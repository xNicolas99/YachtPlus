import aiodocker
from aiodocker.volumes import DockerVolume
from fastapi import HTTPException
import asyncio
import logging
import json
from api.utils.error_handler import safe_http_status, docker_error_detail
from api.settings import get_settings
settings = get_settings()

logger = logging.getLogger(__name__)


def _require_docker_result(result):
    if isinstance(result, aiodocker.exceptions.DockerError):
        raise HTTPException(status_code=safe_http_status(result), detail=docker_error_detail(result)) from result
    if isinstance(result, Exception):
        logger.error("Docker resource request failed", exc_info=(type(result), result, result.__traceback__))
        raise HTTPException(status_code=503, detail="Docker operation failed. Check server logs for details.") from result
    return result


def _container_metadata(result):
    # DockerContainers.list() returns DockerContainer objects with the list
    # metadata already attached; no extra inspect request is necessary.
    containers = _require_docker_result(result)
    return [item if isinstance(item, dict) else item._container for item in containers]


### IMAGES ###

async def get_images(offset: int = 0, limit: int = 100):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        containers_task = docker.containers.list(all=True)
        images_task = docker.images.list()

        results = await asyncio.gather(containers_task, images_task, return_exceptions=True)

        containers = _container_metadata(results[0])

        images = _require_docker_result(results[1])

        used_image_ids = set()
        for container in containers:
            if isinstance(container, dict) and 'ImageID' in container:
                 used_image_ids.add(container['ImageID'])

        image_list = []
        for image in images:
            if not isinstance(image, dict):
                continue

            attrs = image.copy()

            # Robustly handle missing RepoTags or malformed data if necessary
            # The prompt mentioned "failed image tags", likely referring to None or weird values
            if 'RepoTags' not in attrs or attrs['RepoTags'] is None:
                attrs['RepoTags'] = []

            is_in_use = attrs.get('Id') in used_image_ids

            attrs['inUse'] = is_in_use
            image_list.append(attrs)

        total = len(image_list)
        capped_limit = max(limit, 0)
        if capped_limit > 500:
            capped_limit = 500
        if offset < 0:
            offset = 0
        return {"items": image_list[offset:offset + capped_limit], "total": total}


async def write_image(image_tag):
    # Previously: `if delim in image_tag` -> TypeError when image_tag is
    # None (Pydantic schema treats the field as Optional). Catch the
    # missing/blank input early and surface it as a 422.
    if not image_tag or not isinstance(image_tag, str) or not image_tag.strip():
        raise HTTPException(status_code=422, detail="Image name is required")
    image_tag = image_tag.strip()

    # A colon in the registry host is a port, not an image tag. Digests
    # already identify an exact image and must not receive a :latest suffix.
    image_name = image_tag
    if "@" not in image_tag and ":" not in image_tag.rsplit("/", 1)[-1]:
        image_name = f"{image_tag}:latest"

    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        try:
            await docker.images.pull(image_name)
        except Exception as exc:
             raise HTTPException(status_code=500, detail="Docker operation failed. Check server logs for details.")

    return await get_images()


async def get_image(image_id):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        containers_task = docker.containers.list(all=True)
        image_task = docker.images.inspect(image_id)

        try:
            results = await asyncio.gather(containers_task, image_task, return_exceptions=True)

            containers = _container_metadata(results[0])

            if isinstance(results[1], Exception):
                 if isinstance(results[1], aiodocker.exceptions.DockerError):
                     raise HTTPException(status_code=safe_http_status(results[1]), detail=docker_error_detail(results[1]))
                 raise HTTPException(status_code=500, detail="Docker operation failed. Check server logs for details.")
            else:
                 image = results[1]

        except HTTPException:
            raise
        except Exception as exc:
             raise HTTPException(status_code=500, detail="Docker operation failed. Check server logs for details.")

        attrs = image.copy()

        used_image_ids = set()
        for container in containers:
             if isinstance(container, dict) and 'ImageID' in container:
                 used_image_ids.add(container['ImageID'])

        attrs['inUse'] = attrs.get('Id') in used_image_ids
        return attrs


async def update_image(image_id):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        try:
            image = await docker.images.inspect(image_id)
            if image.get('RepoTags'):
                tag = image['RepoTags'][0]
                await docker.images.pull(tag)
        except aiodocker.exceptions.DockerError as exc:
            raise HTTPException(
                status_code=safe_http_status(exc), detail=docker_error_detail(exc)
            )
    return await get_image(image_id)


async def delete_image(image_id):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        try:
             image = await docker.images.inspect(image_id)
             await docker.images.delete(image_id, force=True)
             return image
        except aiodocker.exceptions.DockerError as exc:
            raise HTTPException(
                status_code=safe_http_status(exc), detail=docker_error_detail(exc)
            )


### Volumes ###
async def get_volumes(offset: int = 0, limit: int = 100):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        containers_task = docker.containers.list(all=True)
        volumes_task = docker.volumes.list()

        results = await asyncio.gather(containers_task, volumes_task, return_exceptions=True)

        containers = _container_metadata(results[0])

        volumes_data = _require_docker_result(results[1])

        volumes = volumes_data.get('Volumes', []) or []

        used_volumes = set()
        for container in containers:
            if not isinstance(container, dict):
                continue
            for mount in container.get('Mounts', []):
                 if mount.get('Type') == 'volume':
                     used_volumes.add(mount.get('Name'))

        volume_list = []
        for volume in volumes:
            attrs = volume.copy()
            attrs['inUse'] = attrs.get('Name') in used_volumes
            volume_list.append(attrs)

        total = len(volume_list)
        capped_limit = max(limit, 0)
        if capped_limit > 500:
            capped_limit = 500
        if offset < 0:
            offset = 0
        return {"items": volume_list[offset:offset + capped_limit], "total": total}


async def write_volume(volume_name):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        try:
            await docker.volumes.create({"Name": volume_name})
        except aiodocker.exceptions.DockerError as exc:
            raise HTTPException(
                status_code=safe_http_status(exc), detail=docker_error_detail(exc)
            )
    return await get_volumes()


async def get_volume(volume_name):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        containers_task = docker.containers.list(all=True)
        volume_task = _inspect_volume(docker, volume_name)

        try:
            results = await asyncio.gather(containers_task, volume_task, return_exceptions=True)

            containers = _container_metadata(results[0])

            if isinstance(results[1], Exception):
                 exc = results[1]
                 if isinstance(exc, aiodocker.exceptions.DockerError):
                     raise HTTPException(status_code=safe_http_status(exc), detail=docker_error_detail(exc))
                 raise HTTPException(status_code=500, detail="Docker operation failed. Check server logs for details.")
            else:
                 volume = results[1]

        except HTTPException:
             raise

        attrs = volume.copy()
        used_volumes = set()
        for container in containers:
            if not isinstance(container, dict):
                continue
            for mount in container.get('Mounts', []):
                 if mount.get('Type') == 'volume':
                     used_volumes.add(mount.get('Name'))

        attrs['inUse'] = attrs.get('Name') in used_volumes
        return attrs


async def delete_volume(volume_name):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        try:
            volume_obj = DockerVolume(docker, volume_name)
            volume = await volume_obj.show()
            await volume_obj.delete()
            return volume
        except aiodocker.exceptions.DockerError as exc:
            raise HTTPException(
                status_code=safe_http_status(exc), detail=docker_error_detail(exc)
            )


### Networks ###
async def get_networks(offset: int = 0, limit: int = 100):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        containers_task = docker.containers.list(all=True)
        networks_task = docker.networks.list()

        results = await asyncio.gather(containers_task, networks_task, return_exceptions=True)

        containers = _container_metadata(results[0])

        networks = _require_docker_result(results[1])

        used_network_ids = set()
        for container in containers:
             if not isinstance(container, dict):
                 continue
             net_settings = container.get('NetworkSettings', {})
             for net_name, net_conf in net_settings.get('Networks', {}).items():
                 if 'NetworkID' in net_conf:
                     used_network_ids.add(net_conf['NetworkID'])

        network_list = []
        for network in networks:
            if not isinstance(network, dict):
                continue
            attrs = network.copy()
            attrs['inUse'] = attrs.get('Id') in used_network_ids

            labels = attrs.get("Labels", {}) or {}
            if labels.get("com.docker.compose.project"):
                attrs["Project"] = labels["com.docker.compose.project"]

            network_list.append(attrs)

        total = len(network_list)
        capped_limit = max(limit, 0)
        if capped_limit > 500:
            capped_limit = 500
        if offset < 0:
            offset = 0
        return {"items": network_list[offset:offset + capped_limit], "total": total}


async def write_network(network_form):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        ipam_config = None
        pool_configs = []

        if network_form.ipv4subnet:
            pool_configs.append({
                "Subnet": network_form.ipv4subnet,
                "Gateway": network_form.ipv4gateway,
                "IPRange": network_form.ipv4range
            })

        if network_form.ipv6_enabled and network_form.ipv6subnet:
             pool_configs.append({
                "Subnet": network_form.ipv6subnet,
                "Gateway": network_form.ipv6gateway,
                "IPRange": network_form.ipv6range
            })

        if pool_configs:
            ipam_config = {
                "Config": pool_configs
            }

        options = {}
        if network_form.network_devices:
            options["parent"] = network_form.network_devices

        config = {
            "Name": network_form.name,
            "Driver": network_form.networkDriver,
            "IPAM": ipam_config,
            "Options": options,
            "Internal": network_form.internal,
            "EnableIPv6": network_form.ipv6_enabled,
            "Attachable": network_form.attachable
        }

        try:
            await docker.networks.create(config)
        except aiodocker.exceptions.DockerError as exc:
             raise HTTPException(
                status_code=safe_http_status(exc), detail=docker_error_detail(exc)
            )

    return await get_networks()


async def _inspect_network(docker, network_id):
    # DockerNetworks has no inspect method. get() resolves a network by name
    # or ID and returns an object whose show() retrieves its metadata.
    network_obj = await docker.networks.get(network_id)
    return await network_obj.show()


async def _inspect_volume(docker, volume_name):
    volume_obj = DockerVolume(docker, volume_name)
    return await volume_obj.show()


async def get_network(network_id):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        containers_task = docker.containers.list(all=True)
        network_task = _inspect_network(docker, network_id)

        try:
            results = await asyncio.gather(containers_task, network_task, return_exceptions=True)
            containers = _container_metadata(results[0])

            if isinstance(results[1], Exception):
                 exc = results[1]
                 if isinstance(exc, aiodocker.exceptions.DockerError):
                      raise HTTPException(status_code=safe_http_status(exc), detail=docker_error_detail(exc))
                 raise HTTPException(status_code=500, detail="Docker operation failed. Check server logs for details.")
            else:
                 network = results[1]

        except HTTPException:
            raise

        attrs = network.copy()
        used_network_ids = set()
        for container in containers:
             if not isinstance(container, dict):
                 continue
             net_settings = container.get('NetworkSettings', {})
             for net_name, net_conf in net_settings.get('Networks', {}).items():
                 if 'NetworkID' in net_conf:
                     used_network_ids.add(net_conf['NetworkID'])

        attrs['inUse'] = attrs.get('Id') in used_network_ids
        return attrs


async def delete_network(network_id):
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        try:
            network_obj = await docker.networks.get(network_id)
            network = await network_obj.show()
            await network_obj.delete()
            return network
        except aiodocker.exceptions.DockerError as exc:
             raise HTTPException(
                status_code=safe_http_status(exc), detail=docker_error_detail(exc)
            )

async def prune_resources(resource):
    paths = {
        "images": "images/prune",
        "containers": "containers/prune",
        "volumes": "volumes/prune",
        "networks": "networks/prune",
        "build_cache": "build/prune",
    }
    if resource not in paths:
        raise HTTPException(status_code=422, detail="Unsupported resource")
    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        try:
            params = {"filters": json.dumps({"dangling": ["false"]})} if resource == "images" else {}
            return await docker._query_json(paths[resource], method="POST", params=params)
        except aiodocker.exceptions.DockerError as exc:
            raise HTTPException(status_code=safe_http_status(exc), detail=docker_error_detail(exc)) from exc
        except Exception as exc:
            logger.exception("Error pruning %s", resource)
            raise HTTPException(status_code=503, detail="Docker operation failed. Check server logs for details.") from exc
