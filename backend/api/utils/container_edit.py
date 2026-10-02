"""Replace an edited workload only after retaining a recoverable original.

All Docker access uses the caller's configured client. A process-shared lock
serializes edits of the same container across the application's worker pool.
"""
import copy
from contextlib import contextmanager
import hashlib
import logging
import os
from pathlib import Path
import tempfile
import uuid

import docker
from fastapi import HTTPException

from api.utils.container_update import replacement_config, _wait_started

logger = logging.getLogger(__name__)


@contextmanager
def _edit_lock(container_id):
    key = hashlib.sha256(str(container_id).encode()).hexdigest()
    destination = Path(tempfile.gettempdir()) / f"yachtplus-container-edit-{key}.lock"
    descriptor = os.open(destination, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise HTTPException(409, "Another edit is already in progress for this container.") from None
        yield
    finally:
        os.close(descriptor)


def _network_arguments(endpoint):
    kwargs = {}
    if endpoint.get("Aliases"):
        kwargs["aliases"] = endpoint["Aliases"]
    ipam = endpoint.get("IPAMConfig") or {}
    for source, destination in (("IPv4Address", "ipv4_address"), ("IPv6Address", "ipv6_address")):
        if ipam.get(source):
            kwargs[destination] = ipam[source]
    if endpoint.get("DriverOpts"):
        kwargs["driver_opt"] = endpoint["DriverOpts"]
    return kwargs


def _reuse_volume_names(options, attributes):
    volumes = options.get("volumes")
    if volumes is None:
        volumes = {}
    if not isinstance(volumes, dict):
        # The form converter emits a dict. Refuse an ambiguous structure
        # before stopping anything rather than guessing its destinations.
        raise HTTPException(422, "Edited container volumes must be a mapping.")
    volumes = copy.deepcopy(volumes)
    destinations = set()
    for binding in volumes.values():
        if not isinstance(binding, dict) or not isinstance(binding.get("bind"), str):
            raise HTTPException(422, "Edited volume mappings require a destination.")
        destinations.add(binding["bind"])
    for mount in attributes.get("Mounts") or []:
        if mount.get("Type") != "volume" or mount.get("Destination") in destinations:
            continue
        if not mount.get("Name") or not mount.get("Destination"):
            raise HTTPException(422, "Cannot preserve the existing container volume.")
        if mount["Name"] in volumes:
            # The same source can legitimately be mounted at two targets;
            # a short-form dictionary cannot represent both without silently
            # overwriting the requested binding. Preserve it as a long mount.
            options.setdefault("mounts", []).append(docker.types.Mount(
                target=mount["Destination"], source=mount["Name"], type="volume",
                read_only=not mount.get("RW", True),
            ))
        else:
            volumes[mount["Name"]] = {"bind": mount["Destination"], "mode": "rw" if mount.get("RW", True) else "ro"}
        destinations.add(mount["Destination"])
    options["volumes"] = volumes


def edit_container(client, original, launch_options):
    with _edit_lock(original.id):
        return _edit_container_locked(client, original, launch_options)


def _edit_container_locked(client, original, launch_options):
    original.reload()
    attributes = copy.deepcopy(original.attrs)
    original_name = attributes["Name"].lstrip("/")
    options = copy.deepcopy(launch_options)
    transaction_id = uuid.uuid4().hex
    options["labels"] = dict(options.get("labels") or {})
    options["labels"]["local.yachtplus.edit.transaction"] = transaction_id
    candidate_name = options["name"]
    if candidate_name != original_name:
        try:
            collision = client.containers.get(candidate_name)
        except docker.errors.NotFound:
            pass
        else:
            if collision.id != original.id:
                raise HTTPException(409, "The requested container name is already in use.")
    # This also validates AutoRemove and resolves anonymous long mounts before
    # any stop/rename. No insecure compatibility fallback occurs on failure.
    try:
        preserved = replacement_config(attributes)
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    _reuse_volume_names(options, attributes)
    if attributes.get("Config", {}).get("Healthcheck"):
        options["healthcheck"] = copy.deepcopy(attributes["Config"]["Healthcheck"])
    endpoints = preserved.get("NetworkingConfig", {}).get("EndpointsConfig", {})
    networks = [(name, client.networks.get(name), endpoint) for name, endpoint in endpoints.items() if name not in ("bridge", "host", "none")]
    requested_network = options.get("network")
    requested_mode = options.get("network_mode")
    if requested_network in endpoints and requested_network not in ("bridge", "host", "none"):
        # Docker-py accepts endpoint dictionaries and wraps EndpointsConfig.
        # Preserve static addresses and secondary networks when the requested
        # primary network remains unchanged.
        options["networking_config"] = copy.deepcopy(endpoints)
    elif not requested_network and not requested_mode:
        old_mode = attributes.get("HostConfig", {}).get("NetworkMode")
        if old_mode in endpoints and old_mode not in ("bridge", "host", "none"):
            options["network"] = old_mode
            options["networking_config"] = copy.deepcopy(endpoints)
    # Pulling must succeed before interrupting the original. Pin the resolved
    # image so another deployment cannot move its tag during the transaction.
    image = client.images.pull(options["image"])
    options["image"] = image.id
    backup_name = f"{original_name}_edit_backup_{original.id[:12]}"
    was_running = attributes.get("State", {}).get("Running", False)
    replacement = None
    renamed = False
    disconnected = []
    creation_attempted = False
    try:
        if was_running:
            original.stop(timeout=30)
        original.rename(backup_name)
        renamed = True
        for _, network, endpoint in networks:
            network.disconnect(original)
            disconnected.append((network, endpoint))
        # Retain the exact returned object before start. Unlike run(), this
        # makes cleanup after a start failure provably belong to this edit.
        create_options = dict(options)
        create_options.pop("detach", None)
        creation_attempted = True
        replacement = client.containers.create(**create_options)
        replacement.start()
        _wait_started(replacement)
    except Exception as error:
        failures = []

        def restore(stage, operation):
            try:
                operation()
            except Exception:
                failures.append(stage)
                logger.exception("Container edit rollback failed at %s", stage)

        if replacement is None and creation_attempted:
            # A create request may succeed at Docker while its response or
            # subsequent inspect fails. Only our unpredictable transaction
            # label proves that a discovered container belongs to this edit.
            try:
                uncertain = client.containers.get(candidate_name)
                uncertain.reload()
                ownership = uncertain.attrs.get("Config", {}).get("Labels", {}) or {}
                if uncertain.id != original.id and ownership.get("local.yachtplus.edit.transaction") == transaction_id:
                    replacement = uncertain
            except docker.errors.NotFound:
                pass
            except Exception:
                failures.append("inspect uncertain replacement")
                logger.exception("Could not inspect an uncertain edit replacement")

        if replacement is not None and replacement.id != original.id:
            restore("stop replacement", lambda: replacement.stop(timeout=10))
            restore("remove replacement", lambda: replacement.remove(force=True, v=False))
        if renamed:
            restore("restore original name", lambda: original.rename(original_name))
        for network, endpoint in disconnected:
            restore("restore original network", lambda network=network, endpoint=endpoint: network.connect(original, **_network_arguments(endpoint)))
        if was_running:
            restore("restart original", original.start)
        if failures:
            raise HTTPException(502, "Container edit failed and rollback reported errors. The original is retained; inspect server logs.") from error
        raise
    # Replacement is already healthy/running: cleanup failure must not report
    # a failed deployment or delete its persisted data.
    try:
        original.remove(v=False)
    except Exception:
        logger.warning("Container edit succeeded; original backup %s retained.", backup_name, exc_info=True)
    return replacement
