"""Container update worker using the configured Docker API, never a socket mount.

Run in a disposable copy of YachtPlus's existing image so updating YachtPlus
itself survives replacement of the API process. Keep the old container until
the replacement starts successfully; retain its volumes and security options.
"""
import copy
import logging
import os
import time
import uuid
from urllib.parse import urlsplit

import docker

logger = logging.getLogger(__name__)
UPDATE_IMAGE_LABEL = "local.yachtplus.update.image"


def validate_update_target(attrs, endpoint):
    """Do not replace the worker's control channel or mandatory protection."""
    role = (attrs.get("Config", {}).get("Labels") or {}).get("local.yachtplus.infrastructure")
    if role in ("docker-proxy", "fail2ban"):
        raise ValueError("Update security infrastructure through its Compose deployment.")
    hostname = urlsplit(endpoint or "").hostname
    names = {attrs.get("Name", "").lstrip("/").lower()}
    for network in attrs.get("NetworkSettings", {}).get("Networks", {}).values():
        names.update(value.lower() for value in (network.get("Aliases") or []) + (network.get("DNSNames") or []) if isinstance(value, str))
        names.update(value.lower() for value in (network.get("IPAddress"), network.get("GlobalIPv6Address")) if isinstance(value, str) and value)
    if hostname and hostname.lower() in names:
        raise ValueError("The configured Docker proxy cannot update itself through its own API.")


def update_image_reference(config):
    return (config.get("Labels") or {}).get(UPDATE_IMAGE_LABEL) or config["Image"]


def proxy_endpoint(endpoint):
    parsed = urlsplit(endpoint or "")
    if (
        parsed.scheme not in ("tcp", "http", "https") or not parsed.hostname
        or parsed.username or parsed.password or parsed.path not in ("", "/")
        or parsed.query or parsed.fragment
    ):
        raise ValueError("Updates require a configured TCP Docker socket proxy.")
    # Evaluate port here: malformed ports must fail before a worker is started.
    _ = parsed.port
    return endpoint


def replacement_config(attrs):
    config = copy.deepcopy(attrs["Config"])
    # Fields returned by inspect that are not create-container inputs.
    for key in ("OnBuild", "ArgsEscaped"):
        config.pop(key, None)
    if config.get("Hostname") in (attrs.get("Id"), attrs.get("Id", "")[:12]):
        # Docker generates HOSTNAME from the NEW ID when omitted. Retaining
        # the old generated hostname breaks YachtPlus's next self-ID lookup.
        config.pop("Hostname", None)
    host = copy.deepcopy(attrs["HostConfig"])
    if host.get("AutoRemove"):
        raise ValueError("Auto-remove containers cannot be updated with rollback.")
    # Preserve anonymous volumes by binding their existing volume names.
    # Otherwise Docker would create new empty volumes for Config.Volumes.
    binds = list(host.get("Binds") or [])
    destinations = {entry.split(":")[1] for entry in binds if ":" in entry}
    mounts = host.get("Mounts") or []
    existing = {mount.get("Destination"): mount for mount in attrs.get("Mounts", [])}
    for mount in mounts:
        if mount.get("Type") == "volume" and not mount.get("Source"):
            original = existing.get(mount.get("Target"), {})
            if not original.get("Name"):
                raise ValueError("Cannot preserve an anonymous volume without its existing name.")
            mount["Source"] = original["Name"]
    destinations.update(m.get("Target") for m in mounts)
    for mount in attrs.get("Mounts", []):
        destination = mount.get("Destination")
        if mount.get("Type") == "volume" and destination not in destinations:
            name = mount.get("Name")
            if not name:
                raise ValueError("Cannot preserve a container volume without its name.")
            binds.append(f"{name}:{destination}:{'rw' if mount.get('RW', True) else 'ro'}")
    host["Binds"] = binds
    config["HostConfig"] = host
    endpoints = {}
    for name, endpoint in attrs.get("NetworkSettings", {}).get("Networks", {}).items():
        # Dynamic IPs, endpoint IDs and generated ID aliases cannot be reused.
        aliases = [a for a in endpoint.get("Aliases") or [] if a != attrs.get("Id", "")[:12]]
        entry = {"Aliases": aliases} if aliases else {}
        if endpoint.get("IPAMConfig"):
            entry["IPAMConfig"] = copy.deepcopy(endpoint["IPAMConfig"])
        if endpoint.get("DriverOpts"):
            entry["DriverOpts"] = copy.deepcopy(endpoint["DriverOpts"])
        endpoints[name] = entry
    if endpoints:
        config["NetworkingConfig"] = {"EndpointsConfig": endpoints}
    return config


def _wait_started(container, timeout=180):
    deadline = time.monotonic() + timeout
    while True:
        container.reload()
        state = container.attrs.get("State", {})
        if not state.get("Running"):
            raise RuntimeError("Replacement container exited during startup.")
        health = state.get("Health", {}).get("Status")
        if health == "healthy":
            return
        if health == "unhealthy":
            raise RuntimeError("Replacement container failed its health check.")
        if health is None:
            # A running process without a healthcheck can only be checked for
            # immediate exit; do not advertise this as application health.
            time.sleep(2)
            container.reload()
            if not container.attrs.get("State", {}).get("Running"):
                raise RuntimeError("Replacement container exited during startup.")
            return
        if time.monotonic() >= deadline:
            raise RuntimeError("Replacement container startup timed out.")
        time.sleep(2)


def update_container(client, name):
    old = client.containers.get(name)
    old.reload()
    attrs = copy.deepcopy(old.attrs)
    validate_update_target(attrs, os.environ.get("DOCKER_HOST"))
    config = replacement_config(attrs)  # validate before pulling/stopping anything
    reference = update_image_reference(config)
    image = client.images.pull(reference)
    if image.id == attrs.get("Image"):
        return {"updated": False}
    # Pin the actual pulled image so a mutable tag cannot change mid-update.
    config["Image"] = image.id
    config["Labels"] = dict(config.get("Labels") or {})
    config["Labels"][UPDATE_IMAGE_LABEL] = reference
    transaction = uuid.uuid4().hex
    config["Labels"]["local.yachtplus.update.transaction"] = transaction
    was_running = attrs.get("State", {}).get("Running", False)
    backup_name = f"{name}_rollback_{old.id[:12]}"
    replacement = None
    renamed = False
    disconnected = []
    try:
        if was_running:
            old.stop(timeout=30)
        old.rename(backup_name)
        renamed = True
        # Release allocated static IPs and aliases while retaining the old
        # container for rollback. Docker otherwise rejects the new endpoint.
        for network_name, endpoint in config.get("NetworkingConfig", {}).get("EndpointsConfig", {}).items():
            if network_name in ("bridge", "host", "none"):
                continue
            network = client.networks.get(network_name)
            network.disconnect(old)
            disconnected.append((network, endpoint))
        result = client.api.create_container_from_config(config, name=name)
        replacement = client.containers.get(result["Id"])
        if was_running:
            replacement.start()
            _wait_started(replacement)
    except Exception as update_error:
        # Never delete volumes during either rollback or successful cleanup.
        failures = []

        def restore(stage, operation):
            try:
                operation()
            except Exception:
                failures.append(stage)
                logger.exception("Container rollback failed at %s", stage)

        if replacement is None and renamed:
            # The daemon may have created it before its response was lost.
            # Only this transaction's label is sufficient proof for removal.
            try:
                candidate = client.containers.get(name)
                candidate.reload()
                if (candidate.attrs.get("Config", {}).get("Labels") or {}).get("local.yachtplus.update.transaction") == transaction:
                    replacement = candidate
            except docker.errors.NotFound:
                pass
            except Exception:
                failures.append("locate replacement")
                logger.exception("Could not locate a replacement after update failure")
        if replacement is not None:
            restore("stop replacement", lambda: replacement.stop(timeout=10))
            restore("remove replacement", lambda: replacement.remove(force=True, v=False))
        if renamed:
            restore("restore original name", lambda: old.rename(name))
        for network, endpoint in disconnected:
            kwargs = {}
            if endpoint.get("Aliases"):
                kwargs["aliases"] = endpoint["Aliases"]
            ipam = endpoint.get("IPAMConfig", {})
            for source, destination in (("IPv4Address", "ipv4_address"), ("IPv6Address", "ipv6_address")):
                if ipam.get(source):
                    kwargs[destination] = ipam[source]
            if endpoint.get("DriverOpts"):
                kwargs["driver_opt"] = endpoint["DriverOpts"]
            restore("restore network", lambda network=network, kwargs=kwargs: network.connect(old, **kwargs))
        if was_running:
            restore("restart original", old.start)
        if failures:
            raise RuntimeError("Update failed and rollback reported errors; original container retained. Inspect updater logs.") from update_error
        raise
    try:
        old.remove(v=False)
    except Exception:
        logger.warning("Updated container is running; original backup %s could not be removed.", backup_name, exc_info=True)
        return {"updated": True, "retained_original": backup_name}
    return {"updated": True}


def main():
    endpoint = proxy_endpoint(os.environ.get("DOCKER_HOST"))
    name = os.environ["YACHT_UPDATE_TARGET"]
    with docker.DockerClient(base_url=endpoint, timeout=60) as client:
        update_container(client, name)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        main()
    except Exception:
        logger.exception("Container update failed; check the retained original container.")
        raise
