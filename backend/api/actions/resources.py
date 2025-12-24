import aiodocker
from fastapi import HTTPException
import asyncio

### IMAGES ###

async def get_images():
    async with aiodocker.Docker() as docker:
        containers_task = docker.containers.list(all=True)
        images_task = docker.images.list()

        containers, images = await asyncio.gather(containers_task, images_task)

        used_image_ids = set()
        for container in containers:
            if 'ImageID' in container:
                 used_image_ids.add(container['ImageID'])

        image_list = []
        for image in images:
            attrs = image.copy()

            is_in_use = attrs.get('Id') in used_image_ids

            attrs['inUse'] = is_in_use
            image_list.append(attrs)

        return image_list


async def write_image(image_tag):
    delim = ":"
    repo, tag = None, image_tag
    if delim in image_tag:
        repo, tag = tag.split(delim, 1)
    else:
        repo = image_tag
        tag = "latest"

    async with aiodocker.Docker() as docker:
        try:
            await docker.images.pull(f"{repo}:{tag}")
        except Exception as exc:
             raise HTTPException(status_code=500, detail=str(exc))

    return await get_images()


async def get_image(image_id):
    async with aiodocker.Docker() as docker:
        containers_task = docker.containers.list(all=True)
        try:
            image_task = docker.images.inspect(image_id)
            containers, image = await asyncio.gather(containers_task, image_task)
        except aiodocker.exceptions.DockerError as exc:
             raise HTTPException(status_code=exc.status, detail=exc.message)

        attrs = image.copy()

        used_image_ids = set()
        for container in containers:
             if 'ImageID' in container:
                 used_image_ids.add(container['ImageID'])

        attrs['inUse'] = attrs.get('Id') in used_image_ids
        return attrs


async def update_image(image_id):
    async with aiodocker.Docker() as docker:
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
    async with aiodocker.Docker() as docker:
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
    async with aiodocker.Docker() as docker:
        containers_task = docker.containers.list(all=True)
        volumes_task = docker.volumes.list()

        containers, volumes_data = await asyncio.gather(containers_task, volumes_task)
        volumes = volumes_data.get('Volumes', []) or []

        used_volumes = set()
        for container in containers:
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
    async with aiodocker.Docker() as docker:
        try:
            await docker.volumes.create({"Name": volume_name})
        except aiodocker.exceptions.DockerError as exc:
            raise HTTPException(
                status_code=exc.status, detail=exc.message
            )
    return await get_volumes()


async def get_volume(volume_name):
    async with aiodocker.Docker() as docker:
        containers_task = docker.containers.list(all=True)
        volume_task = docker.volumes.inspect(volume_name)

        try:
            containers, volume = await asyncio.gather(containers_task, volume_task)
        except aiodocker.exceptions.DockerError as exc:
             if exc.status == 404:
                  pass
             raise HTTPException(status_code=exc.status, detail=exc.message)

        attrs = volume.copy()
        used_volumes = set()
        for container in containers:
            for mount in container.get('Mounts', []):
                 if mount.get('Type') == 'volume':
                     used_volumes.add(mount.get('Name'))

        attrs['inUse'] = attrs.get('Name') in used_volumes
        return attrs


async def delete_volume(volume_name):
    async with aiodocker.Docker() as docker:
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
    async with aiodocker.Docker() as docker:
        containers_task = docker.containers.list(all=True)
        networks_task = docker.networks.list()

        containers, networks = await asyncio.gather(containers_task, networks_task)

        used_network_ids = set()
        for container in containers:
             net_settings = container.get('NetworkSettings', {})
             for net_name, net_conf in net_settings.get('Networks', {}).items():
                 if 'NetworkID' in net_conf:
                     used_network_ids.add(net_conf['NetworkID'])

        network_list = []
        for network in networks:
            attrs = network.copy()
            attrs['inUse'] = attrs.get('Id') in used_network_ids

            labels = attrs.get("Labels", {}) or {}
            if labels.get("com.docker.compose.project"):
                attrs["Project"] = labels["com.docker.compose.project"]

            network_list.append(attrs)

        return network_list


async def write_network(network_form):
    async with aiodocker.Docker() as docker:
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


async def get_network(network_id):
    async with aiodocker.Docker() as docker:
        containers_task = docker.containers.list(all=True)
        network_task = docker.networks.inspect(network_id)

        try:
            containers, network = await asyncio.gather(containers_task, network_task)
        except aiodocker.exceptions.DockerError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.message)

        attrs = network.copy()
        used_network_ids = set()
        for container in containers:
             net_settings = container.get('NetworkSettings', {})
             for net_name, net_conf in net_settings.get('Networks', {}).items():
                 if 'NetworkID' in net_conf:
                     used_network_ids.add(net_conf['NetworkID'])

        attrs['inUse'] = attrs.get('Id') in used_network_ids
        return attrs


async def delete_network(network_id):
    async with aiodocker.Docker() as docker:
        try:
            network = await docker.networks.inspect(network_id)
            await docker.networks.delete(network_id)
            return network
        except aiodocker.exceptions.DockerError as exc:
             raise HTTPException(
                status_code=exc.status, detail=exc.message
            )

async def prune_resources(resource):
    async with aiodocker.Docker() as docker:
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
