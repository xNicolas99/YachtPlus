from os import stat
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
import logging
import aiofiles
from api.settings import Settings

logger = logging.getLogger(__name__)
settings = Settings()

async def get_running_apps():
    apps_list = []
    try:
        async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
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
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        try:
            app = await docker.containers.get(app_name)
            attrs = await app.show()
        except aiodocker.exceptions.DockerError as exc:
             raise HTTPException(status_code=exc.status, detail=exc.message)

        config = attrs.get("Config")
        if config and config.get("Image"):
            loop = asyncio.get_event_loop()
            try:
                # _check_updates performs network I/O, run in executor
                is_updatable = await loop.run_in_executor(None, _check_updates, config["Image"])
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

async def get_apps():
    apps_list = []
    try:
        async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
            try:
                apps = await docker.containers.list(all=True)
            except aiodocker.exceptions.DockerError as exc:
                logger.error(f"Docker API Error in get_apps: {exc.message}")
                raise HTTPException(status_code=exc.status, detail=exc.message)
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
         raise HTTPException(status_code=503, detail=f"Docker Connection Error: {str(e)}")

    return apps_list

async def get_app(app_name):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        try:
            app = await docker.containers.get(app_name)
            attrs = await app.show()
        except aiodocker.exceptions.DockerError as exc:
             raise HTTPException(status_code=exc.status, detail=exc.message)

        attrs["name"] = attrs.get("Name", "")[1:]
        attrs["short_id"] = attrs.get("Id", "")[:12]
        attrs["ports"] = attrs.get("NetworkSettings", {}).get("Ports", {})

        return attrs

async def get_app_processes(app_name):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
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
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
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
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
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
        launch = await launch_app(
            template.name,
            conv_image2data(template.image),
            conv_restart2data(template.restart_policy),
            template.command,
            conv_ports2data(template.ports, template.network, template.network_mode),
            conv_portlabels2data(template.ports),
            template.network_mode,
            template.network,
            conv_volumes2data(template.volumes),
            conv_env2data(template.env),
            conv_devices2data(template.devices),
            conv_labels2data(template.labels),
            conv_sysctls2data(template.sysctls),
            conv_caps2data(template.cap_add),
            conv_cpus2data(template.cpus),
            template.mem_limit,
            edit=template.edit or False,
            _id=template.id or None,
        )
    except HTTPException as exc:
        raise exc
    except (docker.errors.DockerException, aiodocker.exceptions.DockerError) as exc:
        raise exc
    except Exception as exc:
         raise HTTPException(status_code=500, detail=str(exc))

    logs = await launch.log(stdout=True, stderr=True)
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
):
    """
    Deprecated: Use launch_app_from_template instead for cleaner signature.
    Kept for backward compatibility if called from other places, but mapped to new function if possible.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _launch_app_sync,
        name, image, restart_policy, command, ports, portlabels,
        network_mode, network, volumes, env, devices, labels,
        sysctls, caps, cpus, mem_limit, edit, _id
    )

def _launch_app_sync(
    name, image, restart_policy, command, ports, portlabels,
    network_mode, network, volumes, env, devices, labels,
    sysctls, caps, cpus, mem_limit, edit, _id
):
    dclient = docker.from_env()
    if edit == True:
        try:
            dclient.containers.get(_id)
            try:
                running_app = dclient.containers.get(_id)
                running_app.remove(force=True)
            except Exception as e:
                logger.warning(f"Failed to remove existing container {_id} during edit: {e}")
        except Exception:
            # Container might not exist, which is fine
            pass

    combined_labels = Merge(portlabels, labels)
    try:
        launch = dclient.containers.run(
            name=name,
            image=image,
            restart_policy=restart_policy,
            command=command,
            ports=ports,
            network=network,
            network_mode=network_mode,
            volumes=volumes,
            environment=env,
            sysctls=sysctls,
            labels=combined_labels,
            devices=devices,
            cap_add=caps,
            nano_cpus=cpus,
            mem_limit=mem_limit,
            detach=True,
        )

        return AiodockerCompatWrapper(launch)

    except docker.errors.APIError as e:
        if e.status_code == 500:
            try:
                failed_app = dclient.containers.get(name)
                failed_app.remove()
            except Exception as remove_err:
                logger.error(f"Failed to cleanup container {name} after API error: {remove_err}")
        raise HTTPException(
            status_code=e.status_code, detail=e.explanation
        )

class AiodockerCompatWrapper:
    def __init__(self, container):
        self.container = container

    async def log(self, stdout=True, stderr=True):
        logs = self.container.logs(stdout=stdout, stderr=stderr)
        if isinstance(logs, bytes):
            return [logs.decode('utf-8')]
        return [logs]


async def app_action(app_name, action, background_tasks=None):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        try:
            app = await docker.containers.get(app_name)
        except aiodocker.exceptions.DockerError as exc:
             raise HTTPException(status_code=exc.status, detail=exc.message)

        try:
            async with aiofiles.open("/proc/self/cgroup", "r") as f:
                content = await f.readline()
                self_id = content.strip().split("/")[-1]
        except Exception as e:
            logger.debug(f"Could not read self cgroup ID: {e}")
            self_id = None

        c_info = await app.show()
        c_id = c_info['Id']
        c_short_id = c_id[:12]

        if self_id and (c_id == self_id or c_short_id in self_id) and action == "restart":
            if background_tasks:
                 background_tasks.add_task(app.restart, timeout=10)
            else:
                 asyncio.create_task(app.restart(timeout=10))

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
            raise HTTPException(status_code=exc.status, detail=exc.message)

    return await get_apps()

async def app_update(app_name):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        try:
            old = await docker.containers.get(app_name)
            old_info = await old.show()
            old_name = old_info["Name"][1:]
        except aiodocker.exceptions.DockerError as exc:
             raise HTTPException(status_code=exc.status, detail=exc.message)

        config = {
            "Image": "containrrr/watchtower:latest",
            "Cmd": ["--cleanup", "--run-once", old_name],
            "HostConfig": {
                "Binds": ["/var/run/docker.sock:/var/run/docker.sock"],
                "AutoRemove": True
            }
        }

        try:
            updater = await docker.containers.create_or_replace(
                name=f"watchtower_{old_name}",
                config=config
            )
            await updater.start()
            await updater.wait(timeout=120)

        except aiodocker.exceptions.DockerError as exc:
             raise HTTPException(status_code=exc.status, detail=exc.message)

    await asyncio.sleep(1)
    return await get_apps()

async def _get_self_id():
    try:
        async with aiofiles.open("/proc/self/cgroup", "r") as f:
            content = await f.readline()
            return content.strip().split("/")[-1]
    except Exception as e:
        logger.warning(f"Failed to determine self container ID: {e}")
        return None

async def _update_self(background_tasks):
    yacht_id = await _get_self_id()
    if not yacht_id:
         raise HTTPException(status_code=404, detail="Unable to get Yacht container ID")

    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        try:
            yacht = await docker.containers.get(yacht_id)
            yacht_info = await yacht.show()
            yacht_name = yacht_info["Name"][1:]
        except aiodocker.exceptions.DockerError:
             raise HTTPException(status_code=404, detail="Unable to get Yacht container ID")

    background_tasks.add_task(update_self_in_background, yacht_name)
    return {"result": "successful"}

async def update_self_in_background(yacht_name):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        print("**** Updating " + yacht_name + "****")
        config = {
            "Image": "containrrr/watchtower:latest",
            "Cmd": ["--cleanup", "--run-once", yacht_name],
            "HostConfig": {
                "Binds": ["/var/run/docker.sock:/var/run/docker.sock"],
                "AutoRemove": True
            }
        }
        try:
            updater = await docker.containers.create(config=config)
            await updater.start()
        except Exception as e:
            logger.error(f"Error updating self: {e}")

async def check_self_update():
    yacht_id = await _get_self_id()
    if not yacht_id:
         raise HTTPException(status_code=404, detail="Unable to get Yacht container ID")

    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        try:
            yacht = await docker.containers.get(yacht_id)
            info = await yacht.show()
            tag = info["Config"]["Image"]
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _check_updates, tag)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))


async def generate_support_bundle(app_name):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
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
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        try:
            container = await docker.containers.get(app_name)
            info = await container.show()
            if info["State"]["Status"] == "running":
                async for line in container.log(stdout=True, stderr=True, follow=True, tail=200):
                    yield {"event": "update", "retry": 3000, "data": line}
                    if await request.is_disconnected():
                        break
        except aiodocker.exceptions.DockerError:
            pass

async def stat_generator(request, app_name):
    prev_stats = None
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as adocker:
        try:
            container = await adocker.containers.get(app_name)
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
            pass

async def all_stat_generator(request):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
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

    loops = [stat_generator(request, name) for name in running_names]

    if not loops:
        return

    async with aiostream.stream.merge(*loops).stream() as merged:
        async for event in merged:
            yield event

async def process_app_stats(line, app_name):
    cpu_total = 0.0
    cpu_system = 0.0
    cpu_percent = 0.0

    if "memory_stats" in line:
        mem_current = line["memory_stats"].get("usage", 0)
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
