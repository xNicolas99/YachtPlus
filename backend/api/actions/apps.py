from api.utils.container_stats import memory_usage
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from api.db.schemas.apps import DeployLogs, DeployForm, AppLogs, Processes
from api.utils.apps import (
    conv_caps2data,
    conv_devices2data,
    conv_env2data,
    conv_image2data,
    conv_labels2data,
    conv_portlabels2data,
    conv_ports2data,
    conv_restart2data,
    conv_sysctls2data,
    conv_volumes2data,
    conv_cpus2data,
    _check_updates,
    calculate_cpu_percent,
    calculate_cpu_percent2,
    format_bytes,
)
from api.utils.templates import conv2dict

import yaml
import json
import io
import zipfile
import time
import subprocess
import docker
import aiodocker
import asyncio
import aiostream
from functools import lru_cache
import logging
import aiofiles
import os
import hashlib
from api.settings import get_settings
settings = get_settings()

logger = logging.getLogger(__name__)

async def get_running_apps():
    apps_list = []
    try:
        async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
            apps = await docker.containers.list()
            for app in apps:
                attrs = app._container if hasattr(app, '_container') else app
                if not isinstance(attrs, dict):
                    continue

                name = attrs.get("Names", ["/Unknown"])[0][1:]
                ports = attrs.get("Ports", [])
                short_id = attrs.get("Id", "")[:12]

                attrs.update({"name": name, "ports": ports, "short_id": short_id})
                apps_list.append(attrs)
    except Exception as e:
        logger.error(f"Error fetching running apps: {e}")
        # Retain behavior of returning empty list if docker fails
        pass

    return apps_list

async def check_app_update(app_name):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        try:
            app = await docker.containers.get(app_name)
            attrs = await app.show()
        except aiodocker.exceptions.DockerError as exc:
             raise HTTPException(
                 status_code=_safe_http_status(exc),
                 detail="Docker operation failed. Check server logs for details.",
             )

        config = attrs.get("Config")
        if config and config.get("Image"):
            loop = asyncio.get_event_loop()
            try:
                # _check_updates performs network I/O, run in executor
                from api.utils.container_update import update_image_reference
                is_updatable = await loop.run_in_executor(None, _check_updates, update_image_reference(config))
                if is_updatable:
                    attrs["isUpdatable"] = True
            except Exception as e:
                logger.warning(f"Failed to check for updates for {config.get('Image')}: {e}")

        attrs["name"] = attrs.get("Name", "")[1:]
        attrs["short_id"] = attrs.get("Id", "")[:12]
        attrs["ports"] = attrs.get("NetworkSettings", {}).get("Ports", {})

        return attrs

def normalize_ports(summary_ports):
    """
    Convert Docker Summary ports list to Inspection ports dict format.
    Summary: [{'IP': '0.0.0.0', 'PrivatePort': 80, 'PublicPort': 8000, 'Type': 'tcp'}]
    Inspection: {'80/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '8000'}]}
    """
    if not summary_ports:
        return {}

    # If it's already a dict (Inspection format), return it
    if isinstance(summary_ports, dict):
        return summary_ports

    ports_dict = {}
    for p in summary_ports:
        if not isinstance(p, dict): continue

        private_port = p.get("PrivatePort")
        proto = p.get("Type", "tcp")
        key = f"{private_port}/{proto}"

        host_ip = p.get("IP", "0.0.0.0")
        host_port = str(p.get("PublicPort", ""))

        if key not in ports_dict:
            ports_dict[key] = []

        if host_port:
            ports_dict[key].append({"HostIp": host_ip, "HostPort": host_port})

    return ports_dict

from api.utils.error_handler import safe_http_status as _safe_http_status


def _docker_error_detail(exc: aiodocker.exceptions.DockerError) -> str:
    """Return a client-safe error message for an aiodocker exception.

    The raw `exc.message` may contain daemon paths, internal hostnames, or
    other operational details that should not leave the server. This helper
    preserves the HTTP status via `_safe_http_status` but maps the message
    to a small set of generic, still actionable descriptions.
    """
    # Common aiodocker messages are simple status text; whitelist them so
    # the UI can show useful feedback without exposing internals.
    lower = (exc.message or "").lower()
    if exc.status == 404 or "no such" in lower or "not found" in lower:
        return "Container not found"
    if exc.status == 409 or "conflict" in lower:
        return "Container is in a state that prevents this action"
    if exc.status == 500 and "cannot" in lower:
        return "Container action could not be completed"
    return "Docker operation failed. Check server logs for details."


async def get_apps():
    apps_list = []
    try:
        async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
            try:
                apps = await docker.containers.list(all=True)
            except aiodocker.exceptions.DockerError as exc:
                logger.error(f"Docker API Error in get_apps: {exc.message}")
                raise HTTPException(
                    status_code=_safe_http_status(exc), detail=_docker_error_detail(exc),
                )
            except Exception as exc:
                logger.error(f"Unexpected error in get_apps (Docker connection?): {exc}")
                raise HTTPException(status_code=503, detail="Docker unavailable")

            # Debug log
            logger.debug(f"get_apps: Found {len(apps)} containers via aiodocker")

            for app in apps:
                # Ensure we handle both dicts and objects if aiodocker version changes or behaves oddly
                attrs = app._container if hasattr(app, '_container') else app
                if not isinstance(attrs, dict):
                    logger.warning(f"Skipping app item of type {type(attrs)}")
                    continue

                names = attrs.get("Names")
                if not names:
                     name = "Unknown"
                else:
                     name = names[0][1:] # Strip leading slash

                short_id = attrs.get("Id", "")[:12]

                # Handling Data Structure Mismatches for Frontend

                # 1. Ensure State is a dict with Status (Frontend expects item.State.Status)
                state = attrs.get("State")
                if isinstance(state, str):
                    attrs["State"] = {"Status": state}

                # 2. Ensure Config exists (Frontend expects item.Config.Image, item.Config.Labels)
                if "Config" not in attrs:
                    attrs["Config"] = {
                        "Image": attrs.get("Image"),
                        "Labels": attrs.get("Labels") or {}
                    }

                # 3. Normalize Ports (Frontend expects Dict format)
                # 'Ports' in summary is List. 'ports' (lowercase) is added below.
                raw_ports = attrs.get("Ports", [])

                # Update the main dict
                attrs.update({
                    "name": name,
                    "ports": normalize_ports(raw_ports),
                    "short_id": short_id
                })
                apps_list.append(attrs)

    except HTTPException:
        raise
    except Exception as e:
         logger.error(f"Critical error in get_apps: {e}")
         raise HTTPException(status_code=503, detail="Docker unavailable")

    return apps_list

async def get_app(app_name):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        try:
            app = await docker.containers.get(app_name)
            attrs = await app.show()
        except aiodocker.exceptions.DockerError as exc:
             raise HTTPException(status_code=_safe_http_status(exc), detail=_docker_error_detail(exc))

        attrs["name"] = attrs.get("Name", "")[1:]
        attrs["short_id"] = attrs.get("Id", "")[:12]
        attrs["ports"] = attrs.get("NetworkSettings", {}).get("Ports", {})

        return attrs

async def get_app_processes(app_name):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        try:
            app = await docker.containers.get(app_name)
            attrs = await app.show()
            if attrs["State"]["Status"] == "running":
                 processes = await app.top()
                 return Processes(Processes=processes["Processes"], Titles=processes["Titles"])
            else:
                return Processes(Processes=[], Titles=[])
        except Exception as e:
            logger.error(f"Error fetching processes for {app_name}: {e}")
            # Return empty process list on error instead of None/crashing
            return Processes(Processes=[], Titles=[])

async def get_app_logs(app_name):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        try:
            app = await docker.containers.get(app_name)
            attrs = await app.show()
            if attrs["State"]["Status"] == "running":
                logs = await app.log(stdout=True, stderr=True)
                return AppLogs(logs="".join(logs))
            else:
                return None
        except Exception as e:
            logger.error(f"Error fetching logs for {app_name}: {e}")
            return None

async def check_container_conflicts(data: DeployForm):
    conflicts = []
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        # Check Name
        try:
            c = await docker.containers.get(data.name)
            c_info = await c.show()
            if data.edit and data.id == c_info['Id']:
                pass
            else:
                conflicts.append({"type": "name", "message": f"Container name '{data.name}' is already in use."})
        except aiodocker.exceptions.DockerError as exc:
            if exc.status == 404:
                pass
            else:
                raise

        # Check Ports
        if data.ports:
            requested_ports = set()
            for p in data.ports:
                if p.hport:
                    requested_ports.add((str(p.hport), p.proto))

            if requested_ports:
                existing_containers = await docker.containers.list()
                for c in existing_containers:
                    c_id = c._container.get('Id')

                    if data.edit and data.id == c_id:
                        continue

                    c_ports = c._container.get('Ports', [])
                    if not c_ports: continue

                    c_name = c._container.get("Names", ["/Unknown"])[0][1:]

                    for port_cfg in c_ports:
                        h_port = str(port_cfg.get('PublicPort'))
                        if not h_port: continue
                        proto = port_cfg.get('Type')

                        if (h_port, proto) in requested_ports:
                             conflicts.append({
                                 "type": "port",
                                 "port": h_port,
                                 "message": f"Host port {h_port}/{proto} is already used by container {c_name}"
                             })

    return conflicts

async def deploy_app(template: DeployForm):
    conflicts = await check_container_conflicts(template)
    if conflicts:
        logger.warning(f"Deployment conflicts for {template.name}: {conflicts}")
        return {"success": False, "conflicts": conflicts}

    try:
        # Load TemplateVariables once and share across the three conv_* helpers
        # that need them. Previously each opened its own SessionLocal -> 3 DB
        # roundtrips per deploy. The sync DB read is isolated via to_thread so
        # it never blocks the event loop.
        from api.utils.apps import load_template_variables_async
        t_variables = await load_template_variables_async()

        launch = await launch_app(
            template.name,
            conv_image2data(template.image),
            conv_restart2data(template.restart_policy),
            template.command,
            conv_ports2data(template.ports, template.network, template.network_mode),
            conv_portlabels2data(template.ports),
            template.network_mode,
            template.network,
            conv_volumes2data(template.volumes, t_variables=t_variables),
            conv_env2data(template.env, t_variables=t_variables),
            conv_devices2data(template.devices),
            conv_labels2data(template.labels, t_variables=t_variables),
            conv_sysctls2data(template.sysctls),
            conv_caps2data(template.cap_add),
            conv_cpus2data(template.cpus),
            template.mem_limit,
            edit=template.edit or False,
            _id=template.id or None,
            security_profile=template.security_profile,
            container_user=template.container_user,
            confirm_image_default=template.confirm_image_default,
        )
    except HTTPException as exc:
        raise exc
    except docker.errors.APIError as exc:
        # docker-py gives us a structured status_code + explanation; map
        # it through instead of swallowing it into a generic 500. This is
        # the path most "image not pullable / conflicting name / no such
        # image" deploy failures take.
        logger.warning(
            "Deploy failed (docker APIError): status=%s detail=%s",
            getattr(exc, "status_code", None),
            getattr(exc, "explanation", None),
        )
        raise HTTPException(
            status_code=_safe_http_status(exc),
            detail="Docker deployment failed. Check server logs for details.",
        )
    except (docker.errors.DockerException, aiodocker.exceptions.DockerError) as exc:
        # deploy_app calls launch_app, which still runs the synchronous
        # docker SDK inside a thread-pool executor. Synchronous client
        # errors therefore bubble up alongside aiodocker errors. Keep the
        # union catch so both paths are handled without leaking raw daemon
        # details to the client.
        logger.warning("Deploy failed (docker error): %s", exc)
        raise HTTPException(
            status_code=_safe_http_status(exc),
            detail="Docker deployment failed. Check server logs for details.",
        )
    except Exception:
        # Don't echo the raw exception message to the client (could leak
        # paths or config); log it loudly and return a sanitized 500.
        logger.exception("Unexpected error deploying %s", template.name)
        raise HTTPException(status_code=500, detail="Deploy failed")

    try:
        logs = await launch.log(stdout=True, stderr=True)
    except Exception:
        # A deploy that succeeded but whose log fetch failed should NOT
        # be a 500 — the container is already running. Return an empty
        # log body so the frontend can confirm success.
        logger.exception("Deploy succeeded but log fetch failed for %s", template.name)
        logs = []
    return DeployLogs(logs="".join(logs))

def Merge(dict1, dict2):
    if dict1 and dict2:
        dict2.update(dict1)
        return dict2
    elif dict1:
        return dict1
    elif dict2:
        return dict2
    else:
        return None

async def launch_app(
    name,
    image,
    restart_policy,
    command,
    ports,
    portlabels,
    network_mode,
    network,
    volumes,
    env,
    devices,
    labels,
    sysctls,
    caps,
    cpus,
    mem_limit,
    edit,
    _id,
    security_profile="restricted",
    container_user="1000:1000",
    confirm_image_default=False,
):
    """
    Deprecated: Use launch_app_from_template instead for cleaner signature.
    Kept for backward compatibility if called from other places, but mapped to new function if possible.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _launch_app_sync,
        name, image, restart_policy, command, ports, portlabels,
        network_mode, network, volumes, env, devices, labels,
        sysctls, caps, cpus, mem_limit, edit, _id,
        security_profile, container_user, confirm_image_default
    )

def _launch_app_sync(
    name, image, restart_policy, command, ports, portlabels,
    network_mode, network, volumes, env, devices, labels,
    sysctls, caps, cpus, mem_limit, edit, _id,
    security_profile="restricted", container_user="1000:1000", confirm_image_default=False
):
    from api.utils.container_security import workload_options, ALLOWED_CAPABILITIES
    security_options = workload_options(security_profile, container_user, confirm_image_default)
    if security_profile == "restricted" and (network_mode == "host" or network == "host" or devices):
        raise HTTPException(422, "Host networking and devices require confirmed image compatibility mode.")
    if security_profile == "restricted" and (
        not isinstance(caps or [], list) or any(
            not isinstance(capability, str) or capability.upper().removeprefix("CAP_") not in ALLOWED_CAPABILITIES
            for capability in caps or []
        )
    ):
        raise HTTPException(422, "Restricted containers cannot request elevated capabilities.")
    from api.utils.docker_client import sync_docker_client
    with sync_docker_client() as dclient:
        original = None
        if edit is True:
            try:
                original = dclient.containers.get(_id)
            except docker.errors.NotFound:
                # A genuinely absent original becomes a normal deployment.
                pass
            except docker.errors.APIError as error:
                raise HTTPException(status_code=error.status_code or 502, detail="Cannot inspect the original container before editing.") from error

        if original is not None:
            # An in-process edit must never stop its own API, its only Docker
            # connection, or mandatory protection. These services are changed
            # through their deployment configuration / dedicated updater.
            infrastructure = (original.attrs.get("Config", {}).get("Labels") or {}).get("local.yachtplus.infrastructure")
            self_id = _read_self_id()
            if infrastructure in ("application", "docker-proxy", "fail2ban") or (self_id and original.id.startswith(self_id)):
                raise HTTPException(409, "YachtPlus infrastructure cannot be edited as a workload. Use its deployment configuration.")
            from urllib.parse import urlsplit
            endpoint_host = urlsplit(getattr(get_settings(), "DOCKER_HOST", None) or "").hostname
            if endpoint_host:
                proxy_names = {original.attrs.get("Name", "").lstrip("/").lower()}
                for endpoint in original.attrs.get("NetworkSettings", {}).get("Networks", {}).values():
                    proxy_names.update(alias.lower() for alias in (endpoint.get("Aliases") or []) + (endpoint.get("DNSNames") or []) if isinstance(alias, str))
                    proxy_names.update(value.lower() for value in (endpoint.get("IPAddress"), endpoint.get("GlobalIPv6Address")) if isinstance(value, str) and value)
                if endpoint_host.lower() in proxy_names:
                    raise HTTPException(409, "The configured Docker proxy cannot be edited as a workload. Use its deployment configuration.")

        combined_labels = Merge(portlabels, labels)
        combined_labels = dict(combined_labels or {})
        combined_labels["local.yachtplus.security.profile"] = security_profile
        combined_labels["local.yachtplus.update.image"] = image
        launch_options = {
            "name": name, "image": image, "restart_policy": restart_policy,
            "command": command, "ports": ports, "network": network,
            "network_mode": network_mode, "volumes": volumes, "environment": env,
            "sysctls": sysctls, "labels": combined_labels, "devices": devices,
            "cap_add": caps, "nano_cpus": cpus, "mem_limit": mem_limit,
            "detach": True, **security_options,
        }
        if original is not None:
            from api.utils.container_edit import edit_container
            try:
                launch = edit_container(dclient, original, launch_options)
            except docker.errors.APIError as error:
                raise HTTPException(status_code=error.status_code or 502, detail="Container edit failed. The original container is retained.") from error
            except RuntimeError as error:
                raise HTTPException(502, "Container edit failed. The original container is retained.") from error
            return AiodockerCompatWrapper(launch)
        # run() can create successfully and then fail while starting. Only a
        # unique deployment marker permits cleanup of an uncertain result;
        # looking up the requested name alone could delete an unrelated app.
        import uuid
        deployment_id = uuid.uuid4().hex
        combined_labels["local.yachtplus.deploy.transaction"] = deployment_id
        try:
            launch = dclient.containers.run(**launch_options)

            return AiodockerCompatWrapper(launch)

        except docker.errors.APIError as e:
            if e.status_code == 500:
                try:
                    failed_app = dclient.containers.get(name)
                    failed_app.reload()
                    candidate_labels = failed_app.attrs.get("Config", {}).get("Labels", {}) or {}
                    if candidate_labels.get("local.yachtplus.deploy.transaction") == deployment_id:
                        failed_app.remove(force=True, v=False)
                except docker.errors.NotFound:
                    pass
                except Exception as remove_err:
                    logger.error(f"Failed to cleanup container {name} after API error: {remove_err}")
            raise HTTPException(
                status_code=_safe_http_status(e), detail="Container deployment failed. Check server logs for details."
            )

class AiodockerCompatWrapper:
    def __init__(self, container):
        self.container = container

    async def log(self, stdout=True, stderr=True):
        logs = await asyncio.to_thread(self.container.logs, stdout=stdout, stderr=stderr, tail=10000)
        if isinstance(logs, bytes):
            return [logs.decode('utf-8')]
        return [logs]


async def app_action(app_name, action, background_tasks=None):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        try:
            app = await docker.containers.get(app_name)
        except aiodocker.exceptions.DockerError as exc:
             raise HTTPException(status_code=_safe_http_status(exc), detail=_docker_error_detail(exc))

        self_id = await _get_self_id()

        c_info = await app.show()
        c_id = c_info['Id']
        c_short_id = c_id[:12]

        if self_id and (c_id == self_id or c_short_id in self_id) and action == "restart":
            if background_tasks:
                 background_tasks.add_task(_restart_by_name, c_id)
            else:
                 asyncio.create_task(_restart_by_name(c_id))

            return await get_apps()

        try:
            if action == "start":
                await app.start()
            elif action == "stop":
                await app.stop()
            elif action == "restart":
                await app.restart()
            elif action == "remove":
                await app.delete(force=True)
            elif action == "kill":
                await app.kill()
            elif action == "pause":
                await app.pause()
            elif action == "unpause":
                await app.unpause()
        except aiodocker.exceptions.DockerError as exc:
            raise HTTPException(status_code=_safe_http_status(exc), detail=_docker_error_detail(exc))

    return await get_apps()

async def _restart_by_name(container_id, timeout=10):
    # The request's Docker client has closed by the time BackgroundTasks run.
    try:
        async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
            container = await docker.containers.get(container_id)
            await container.restart(timeout=timeout)
    except Exception:
        logger.exception("Self-restart failed for container %s", container_id)


async def app_update(app_name):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        try:
            old = await docker.containers.get(app_name)
            old_info = await old.show()
            old_name = old_info["Name"][1:]
        except aiodocker.exceptions.DockerError as exc:
             raise HTTPException(status_code=_safe_http_status(exc), detail=_docker_error_detail(exc))

        try:
            updater = await _start_update_worker(docker, old_name)
            result = await updater.wait(timeout=600)
            if result.get("StatusCode") != 0:
                raise HTTPException(502, "Container update failed. The original container is retained for rollback; check updater logs.")
            try:
                await updater.delete()
            except aiodocker.exceptions.DockerError:
                logger.warning("Container update succeeded; completed worker cleanup failed.", exc_info=True)

        except aiodocker.exceptions.DockerError as exc:
             raise HTTPException(status_code=_safe_http_status(exc), detail=_docker_error_detail(exc))

    await asyncio.sleep(1)
    return await get_apps()

@lru_cache(maxsize=1)
def _read_self_id():
    # Container ID is immutable for the process lifetime; cache the
    # /proc/self/cgroup read so we don't hit disk on every self-update call.
    # Modern cgroup v2 containers often return '0::/' rather than an ID.
    # Docker's default HOSTNAME is the container's immutable short ID.
    import re
    hostname = os.environ.get("HOSTNAME", "")
    if re.fullmatch(r"[0-9a-f]{12,64}", hostname):
        return hostname
    try:
        with open("/proc/self/cgroup", "r") as f:
            cgroup_id = f.readline().strip().split("/")[-1]
            return cgroup_id if re.fullmatch(r"[0-9a-f]{64}", cgroup_id) else None
    except Exception as e:
        logger.warning(f"Failed to determine self container ID: {e}")
        return None

async def _get_self_id():
    return _read_self_id()

async def _update_self(background_tasks):
    self_id = await _get_self_id()
    if not self_id:
         raise HTTPException(status_code=404, detail="Unable to get YachtPlus container ID")

    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        try:
            self_container = await docker.containers.get(self_id)
            self_info = await self_container.show()
            self_name = self_info["Name"][1:]
        except aiodocker.exceptions.DockerError:
             raise HTTPException(status_code=404, detail="Unable to get YachtPlus container ID")

        from api.utils.container_update import proxy_endpoint
        try:
            proxy_endpoint(get_settings().DOCKER_HOST)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        network_name = os.environ.get("YACHT_DOCKER_PROXY_NETWORK")
        if not network_name or network_name not in self_info.get("NetworkSettings", {}).get("Networks", {}):
            raise HTTPException(409, "Configure the YachtPlus Docker proxy network before updating.")
        await docker.networks.get(network_name)

    background_tasks.add_task(update_self_in_background, self_name)
    return {"result": "successful"}

async def _start_update_worker(docker, container_name):
    from api.utils.container_update import proxy_endpoint, validate_update_target
    try:
        endpoint = proxy_endpoint(get_settings().DOCKER_HOST)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    network_name = os.environ.get("YACHT_DOCKER_PROXY_NETWORK")
    if not network_name:
        raise HTTPException(409, "Configure YACHT_DOCKER_PROXY_NETWORK before updating containers.")
    target = await docker.containers.get(container_name)
    try:
        validate_update_target(await target.show(), endpoint)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    self_id = await _get_self_id()
    if not self_id:
        raise HTTPException(409, "Cannot determine the YachtPlus image for the update worker.")
    own_container = await docker.containers.get(self_id)
    own_info = await own_container.show()
    await docker.networks.get(network_name)  # validate before creating a worker
    if network_name not in own_info.get("NetworkSettings", {}).get("Networks", {}):
        raise HTTPException(409, "The configured Docker proxy network must be attached to YachtPlus.")
    config = {
        "Image": own_info["Image"],
        "User": "1000:1000",
        "Entrypoint": ["python3", "-m", "api.utils.container_update"],
        "Cmd": [],
        "WorkingDir": "/api",
        "Healthcheck": {"Test": ["NONE"]},
        "Env": [f"DOCKER_HOST={endpoint}", f"YACHT_UPDATE_TARGET={container_name}"],
        "Labels": {"local.yachtplus.update-worker": "true"},
        "HostConfig": {
            "AutoRemove": False,
            "NetworkMode": network_name,
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "PidsLimit": 128,
            "Memory": 256 * 1024 * 1024,
            "Tmpfs": {"/tmp": "rw,nosuid,nodev,size=16m"},
        },
    }
    # A stable name rejects overlapping updates instead of killing an active
    # worker. Successful app updates remove it after collecting exit status;
    # failed/self-update workers retain their logs for operator inspection.
    worker_name = "yachtplus_update_" + hashlib.sha256(container_name.encode()).hexdigest()[:20]
    try:
        previous = await docker.containers.get(worker_name)
    except aiodocker.exceptions.DockerError as exc:
        if getattr(exc, "status", None) != 404:
            raise
    else:
        previous_info = await previous.show()
        if (
            previous_info.get("State", {}).get("Status") in ("exited", "dead")
            and previous_info.get("Config", {}).get("Labels", {}).get("local.yachtplus.update-worker") == "true"
            and previous_info.get("Config", {}).get("Entrypoint") == ["python3", "-m", "api.utils.container_update"]
        ):
            await previous.delete()
        else:
            raise HTTPException(409, "An update worker already exists; wait for completion or inspect its logs.")
    updater = await docker.containers.create(config=config, name=worker_name)
    try:
        await updater.start()
    except Exception:
        await updater.delete(force=True)
        raise
    return updater


async def update_self_in_background(container_name):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        logger.info("**** Updating %s ****", container_name)
        try:
            await _start_update_worker(docker, container_name)
        except Exception as e:
            logger.error(f"Error updating self: {e}")

async def check_self_update():
    self_id = await _get_self_id()
    if not self_id:
         raise HTTPException(status_code=404, detail="Unable to get YachtPlus container ID")

    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        try:
            self_container = await docker.containers.get(self_id)
            info = await self_container.show()
            from api.utils.container_update import update_image_reference
            tag = update_image_reference(info["Config"])
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _check_updates, tag)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Docker operation failed. Check server logs for details.")


async def generate_support_bundle(app_name):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        try:
            app = await docker.containers.get(app_name)
            attrs = await app.show()
            logs = await app.log(stdout=True, stderr=True)
        except aiodocker.exceptions.DockerError:
             raise HTTPException(404, f"App {app_name} not found.")

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zf:
        zf.writestr(f"{app_name}.log", "".join(logs))
        zf.writestr(f"{app_name}-config.yml", yaml.dump(attrs))

    stream.seek(0)
    return StreamingResponse(
        stream,
        media_type="application/x-zip-compressed",
        headers={
            "Content-Disposition": f"attachment;filename={app_name}_bundle.zip"
        },
    )

async def log_generator(request, app_name):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        try:
            container = await docker.containers.get(app_name)
            info = await container.show()
            if info["State"]["Status"] == "running":
                async for line in container.log(stdout=True, stderr=True, follow=True, tail=200):
                    yield {"event": "update", "retry": 3000, "data": line}
                    if await request.is_disconnected():
                        break
            else:
                for line in await container.log(stdout=True, stderr=True, follow=False, tail=200):
                    yield {"event": "update", "data": line}
                yield {"event": "end", "data": "Container stopped"}
        except aiodocker.exceptions.DockerError:
            pass

async def _stat_generator(docker, request, app_name):
    """Yield stat events for one container using an existing aiodocker client."""
    prev_stats = None
    try:
        container = await docker.containers.get(app_name)
        info = await container.show()
        if info["State"]["Status"] == "running":
            async for line in container.stats(stream=True):
                current_stats = await process_app_stats(line, app_name)
                if prev_stats != current_stats:
                    yield {
                        "event": "update",
                        "retry": 30000,
                        "data": json.dumps(current_stats),
                    }
                    prev_stats = current_stats

                if await request.is_disconnected():
                    break
    except Exception as e:
        logger.debug(f"Stat generator stopped for {app_name}: {e}")

async def stat_generator(request, app_name):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as adocker:
        async for event in _stat_generator(adocker, request, app_name):
            yield event

async def all_stat_generator(request):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        containers = await docker.containers.list()

        running_names = []
        for c in containers:
            # Safely access _container or use object itself
            c_dict = c._container if hasattr(c, '_container') else c

            # Check if it's a dict and has State
            if isinstance(c_dict, dict) and c_dict.get("State") == "running":
                # Use Names[0] but strip leading slash
                names = c_dict.get("Names")
                if names:
                    running_names.append(names[0][1:])

        if not running_names:
            return

        loops = [_stat_generator(docker, request, name) for name in running_names]
        async with aiostream.stream.merge(*loops).stream() as merged:
            async for event in merged:
                yield event

async def process_app_stats(line, app_name):
    cpu_total = 0.0
    cpu_system = 0.0
    cpu_percent = 0.0

    if "memory_stats" in line:
        mem_current = memory_usage(line.get("memory_stats", {}))
        mem_total = line["memory_stats"].get("limit", 1)
        mem_percent = (mem_current / mem_total) * 100.0
    else:
        mem_current = None
        mem_total = None
        mem_percent = None

    try:
        cpu_percent, cpu_system, cpu_total = await calculate_cpu_percent2(
            line, cpu_total, cpu_system
        )
    except Exception:
        # calculate_cpu_percent is a fallback
        cpu_percent = await calculate_cpu_percent(line)

    full_stats = {
        "time": line.get("read"),
        "name": app_name,
        "mem_total": mem_total,
        "cpu_percent": round(cpu_percent, 1),
        "mem_current": mem_current,
        "mem_percent": round(mem_percent, 1),
    }
    return full_stats
