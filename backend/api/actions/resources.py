import aiodocker
from fastapi import HTTPException
import asyncio
import logging
from api.settings import Settings

logger = logging.getLogger(__name__)
settings = Settings()

### IMAGES ###

async def get_images():
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        containers_task = docker.containers.list(all=True)
        images_task = docker.images.list()

        results = await asyncio.gather(containers_task, images_task, return_exceptions=True)

        if isinstance(results[0], Exception):
            logger.error(f"Error fetching containers: {results[0]}")
            containers = []
        else:
            containers = results[0]

        if isinstance(results[1], Exception):
            logger.error(f"Error fetching images: {results[1]}")
            images = []
        else:
            images = results[1]

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

        return image_list


async def write_image(image_tag):
    # Previously: `if delim in image_tag` -> TypeError when image_tag is
    # None (Pydantic schema treats the field as Optional). Catch the
    # missing/blank input early and surface it as a 422.
    if not image_tag or not isinstance(image_tag, str) or not image_tag.strip():
        raise HTTPException(status_code=422, detail="Image name is required")
    image_tag = image_tag.strip()

    delim = ":"
    repo, tag = None, image_tag
    if delim in image_tag:
        repo, tag = tag.split(delim, 1)
    else:
        repo = image_tag
        tag = "latest"

    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        try:
            await docker.images.pull(f"{repo}:{tag}")
        except Exception as exc:
             raise HTTPException(status_code=500, detail=str(exc))

    return await get_images()


async def get_image(image_id):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        containers_task = docker.containers.list(all=True)
        image_task = docker.images.inspect(image_id)

        try:
            results = await asyncio.gather(containers_task, image_task, return_exceptions=True)

            if isinstance(results[0], Exception):
                 logger.error(f"Error fetching containers: {results[0]}")
                 containers = []
            else:
                 containers = results[0]

            if isinstance(results[1], Exception):
                 if isinstance(results[1], aiodocker.exceptions.DockerError):
                     raise HTTPException(status_code=results[1].status, detail=results[1].message)
                 raise HTTPException(status_code=500, detail=str(results[1]))
            else:
                 image = results[1]

        except HTTPException:
            raise
        except Exception as exc:
             raise HTTPException(status_code=500, detail=str(exc))

        attrs = image.copy()

        used_image_ids = set()
        for container in containers:
             if isinstance(container, dict) and 'ImageID' in container:
                 used_image_ids.add(container['ImageID'])

        attrs['inUse'] = attrs.get('Id') in used_image_ids
        return attrs


async def update_image(image_id):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        try:
            image = await docker.images.inspect(image_id)
            if image.get('RepoTags'):
                tag = image['RepoTags'][0]
                await docker.images.pull(tag)
        except aiodocker.exceptions.DockerError as exc:
            raise HTTPException(
                status_code=exc.status, detail=exc.message
            )
    return await get_image(image_id)


async def delete_image(image_id):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        try:
             image = await docker.images.inspect(image_id)
             await docker.images.delete(image_id, force=True)
             return image
        except aiodocker.exceptions.DockerError as exc:
            raise HTTPException(
                status_code=exc.status, detail=exc.message
            )


### Volumes ###
async def get_volumes():
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        containers_task = docker.containers.list(all=True)
        volumes_task = docker.volumes.list()

        results = await asyncio.gather(containers_task, volumes_task, return_exceptions=True)

        if isinstance(results[0], Exception):
            logger.error(f"Error fetching containers: {results[0]}")
            containers = []
        else:
            containers = results[0]

        if isinstance(results[1], Exception):
            logger.error(f"Error fetching volumes: {results[1]}")
            volumes_data = {}
        else:
            volumes_data = results[1]

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

        return volume_list


async def write_volume(volume_name):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        try:
            await docker.volumes.create({"Name": volume_name})
        except aiodocker.exceptions.DockerError as exc:
            raise HTTPException(
                status_code=exc.status, detail=exc.message
            )
    return await get_volumes()


async def get_volume(volume_name):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        containers_task = docker.containers.list(all=True)
        volume_task = docker.volumes.inspect(volume_name)

        try:
            results = await asyncio.gather(containers_task, volume_task, return_exceptions=True)

            if isinstance(results[0], Exception):
                 logger.error(f"Error fetching containers: {results[0]}")
                 containers = []
            else:
                 containers = results[0]

            if isinstance(results[1], Exception):
                 exc = results[1]
                 if isinstance(exc, aiodocker.exceptions.DockerError):
                     if exc.status == 404:
                          pass # Handled by calling code? Original code passed here but then raised anyway?
                          # Wait, the original code had:
                          # if exc.status == 404: pass
                          # raise HTTPException...
                          # This means it raised exception anyway unless it was 404 where it passed... to what?
                          # If it passed, `volume` would be undefined.
                          # I will keep the behavior but ensure `volume` is handled.
                          # Actually, if 404, we should probably raise 404.
                     raise HTTPException(status_code=exc.status, detail=exc.message)
                 raise HTTPException(status_code=500, detail=str(exc))
            else:
                 volume = results[1]

        except HTTPException:
             raise

        # If volume is not defined (because of exception handling above being weird in original), check it.
        # But here we either have volume or raised exception.

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
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        try:
            volume = await docker.volumes.inspect(volume_name)
            await docker.volumes.delete(volume_name)
            return volume
        except aiodocker.exceptions.DockerError as exc:
            raise HTTPException(
                status_code=exc.status, detail=exc.message
            )


### Networks ###
async def get_networks():
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        containers_task = docker.containers.list(all=True)
        networks_task = docker.networks.list()

        results = await asyncio.gather(containers_task, networks_task, return_exceptions=True)

        if isinstance(results[0], Exception):
            logger.error(f"Error fetching containers: {results[0]}")
            containers = []
        else:
            containers = results[0]

        if isinstance(results[1], Exception):
            logger.error(f"Error fetching networks: {results[1]}")
            networks = []
        else:
            networks = results[1]

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

        return network_list


async def write_network(network_form):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
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
                status_code=exc.status, detail=exc.message
            )

    return await get_networks()


async def _inspect_network(docker, network_id):
    # aiodocker's `DockerNetworks` does NOT expose `.inspect(id)` — the
    # idiomatic API is `.get(id)` (returns a `DockerNetwork` stub, no
    # request issued yet) followed by `.show()` (issues the actual
    # inspect call). The previous direct `.inspect()` call raised
    # AttributeError on every network-detail page.
    network_obj = await docker.networks.get(network_id)
    return await network_obj.show()


async def get_network(network_id):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        containers_task = docker.containers.list(all=True)
        network_task = _inspect_network(docker, network_id)

        try:
            results = await asyncio.gather(containers_task, network_task, return_exceptions=True)
            if isinstance(results[0], Exception):
                 logger.error(f"Error fetching containers: {results[0]}")
                 containers = []
            else:
                 containers = results[0]

            if isinstance(results[1], Exception):
                 exc = results[1]
                 if isinstance(exc, aiodocker.exceptions.DockerError):
                      raise HTTPException(status_code=exc.status, detail=exc.message)
                 raise HTTPException(status_code=500, detail=str(exc))
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
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        try:
            network = await docker.networks.inspect(network_id)
            await docker.networks.delete(network_id)
            return network
        except aiodocker.exceptions.DockerError as exc:
             raise HTTPException(
                status_code=exc.status, detail=exc.message
            )

async def prune_resources(resource):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        try:
            if resource == "images":
                return await docker.images.prune(filters={'dangling': ['false']})
            elif resource == "containers":
                return await docker.containers.prune()
            elif resource == "volumes":
                return await docker.volumes.prune()
            elif resource == "networks":
                return await docker.networks.prune()
        except Exception as e:
            print(f"Error pruning {resource}: {e}")
            return {"count": 0, "space_reclaimed": 0}
