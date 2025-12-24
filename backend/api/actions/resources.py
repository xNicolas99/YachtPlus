import docker
from fastapi import HTTPException

### IMAGES ###


def get_images():
    dclient = docker.from_env()
    containers = dclient.containers.list(all=True)
    images = dclient.images.list()

    # Pre-calculate used images
    used_image_ids = set()
    for container in containers:
        # container.image triggers an API call.
        # Use container.attrs['Image'] which is the ID string (sha256:...)
        image_id = container.attrs.get('Image')
        if image_id:
            used_image_ids.add(image_id)

    image_list = []
    for image in images:
        attrs = image.attrs
        # Check if this image's ID is in the used set
        # Exact match is better performance-wise
        if image.id in used_image_ids:
            attrs["inUse"] = True
        else:
            attrs["inUse"] = False

        image_list.append(attrs)
    return image_list


def write_image(image_tag):
    delim = ":"
    dclient = docker.from_env()
    repo, tag = None, image_tag
    if delim in image_tag:
        repo, tag = tag.split(delim, 1)
    else:
        repo = image_tag
        tag = "latest"
    image = dclient.images.pull(repo, tag)
    return get_images()


def get_image(image_id):
    dclient = docker.from_env()
    image = dclient.images.get(image_id)
    attrs = image.attrs

    # Check if in use
    containers = dclient.containers.list(all=True)
    in_use = False
    for container in containers:
        # Use attrs['Image'] to avoid API call
        c_image_id = container.attrs.get('Image')
        if c_image_id and c_image_id == image.id:
            in_use = True
            break

    attrs["inUse"] = in_use
    return attrs


def update_image(image_id):
    dclient = docker.from_env()
    if type(image_id) == str:
        image = dclient.images.get(image_id)
        # Check if tags exist
        if not image.tags:
             raise HTTPException(status_code=400, detail="Image has no tags to pull.")

        new_image = dclient.images.get_registry_data(image.tags[0])
        try:
            dclient.images.pull(image.tags[0])
        except Exception as exc:
            # If it's an APIError, it might have response attribute
            if hasattr(exc, 'response'):
                 raise HTTPException(
                    status_code=exc.response.status_code, detail=exc.explanation
                )
            else:
                 raise HTTPException(status_code=500, detail=str(exc))

        return get_image(image_id)


def delete_image(image_id):
    dclient = docker.from_env()
    image = dclient.images.get(image_id)
    try:
        dclient.images.remove(image_id, force=True)
    except Exception as exc:
         if hasattr(exc, 'response'):
            raise HTTPException(
                status_code=exc.response.status_code, detail=exc.explanation
            )
         else:
             raise HTTPException(status_code=500, detail=str(exc))
    return image.attrs


### Volumes ###
def get_volumes():
    dclient = docker.from_env()
    containers = dclient.containers.list(all=True)
    volumes = dclient.volumes.list()

    # Pre-calculate used volumes
    # Set of mount sources (host paths/volume names)
    used_mounts = set()
    for container in containers:
        mounts = container.attrs.get("Mounts", [])
        for m in mounts:
            source = m.get("Source")
            if source:
                used_mounts.add(source)

    volume_list = []
    for volume in volumes:
        attrs = volume.attrs
        mountpoint = attrs.get("Mountpoint")
        # Also check Name, as Source in mounts often matches Name for named volumes
        name = attrs.get("Name")

        if (mountpoint and mountpoint in used_mounts) or (name and name in used_mounts):
             attrs["inUse"] = True
        else:
             attrs["inUse"] = False

        volume_list.append(attrs)
    return volume_list


def write_volume(volume_name):
    dclient = docker.from_env()
    try:
        volume = dclient.volumes.create(name=volume_name)
    except Exception as exc:
        raise HTTPException(
            status_code=exc.response.status_code, detail=exc.explanation
        )
    return get_volumes()


def get_volume(volume_id):
    dclient = docker.from_env()
    volume = dclient.volumes.get(volume_id)
    attrs = volume.attrs

    containers = dclient.containers.list(all=True)
    in_use = False

    mountpoint = attrs.get("Mountpoint")
    name = attrs.get("Name")

    for container in containers:
        mounts = container.attrs.get("Mounts", [])
        for m in mounts:
            source = m.get("Source")
            if source and (source == mountpoint or source == name):
                in_use = True
                break
        if in_use:
            break

    attrs["inUse"] = in_use
    return attrs


def delete_volume(volume_id):
    dclient = docker.from_env()
    volume = dclient.volumes.get(volume_id)
    try:
        volume.remove(force=True)
    except Exception as exc:
        raise HTTPException(
            status_code=exc.response.status_code, detail=exc.explanation
        )
    return volume.attrs


### Networks ###
def get_networks():
    dclient = docker.from_env()
    containers = dclient.containers.list(all=True)
    networks = dclient.networks.list()

    # Pre-calculate used networks
    used_networks = set()
    for container in containers:
        net_settings = container.attrs.get("NetworkSettings", {})
        nets = net_settings.get("Networks", {})
        for net_name, net_data in nets.items():
            net_id = net_data.get("NetworkID")
            if net_id:
                used_networks.add(net_id)

    network_list = []
    for network in networks:
        attrs = network.attrs
        net_id = attrs.get("Id")

        if net_id and net_id in used_networks:
            attrs["inUse"] = True
        else:
            attrs["inUse"] = False

        if attrs.get("Labels", {}):
            if attrs.get("Labels", {}).get("com.docker.compose.project"):
                attrs.update(
                    {"Project": attrs["Labels"]["com.docker.compose.project"]}
                )
        network_list.append(attrs)
    return network_list


def write_network(network_form):
    dclient = docker.from_env()

    ### Check for IP addresses ###
    ipv4_pool = None
    if network_form.ipv4subnet:
        ipv4_pool = docker.types.IPAMPool(
            subnet=network_form.ipv4subnet,
            gateway=network_form.ipv4gateway,
            iprange=network_form.ipv4range,
        )

    ipv6_pool = None
    if network_form.ipv6_enabled and network_form.ipv6subnet:
        ipv6_pool = docker.types.IPAMPool(
            subnet=network_form.ipv6subnet,
            gateway=network_form.ipv6gateway,
            iprange=network_form.ipv6range,
        )

    pool_configs = []
    if ipv4_pool:
        pool_configs.append(ipv4_pool)
    if ipv6_pool:
        pool_configs.append(ipv6_pool)

    ipam_config = docker.types.IPAMConfig(pool_configs=pool_configs) if pool_configs else None

    ### Check for parent device (macvlan only) ###
    if network_form.network_devices:
        network_options = {"parent": network_form.network_devices}
    else:
        network_options = None
    try:
        dclient.networks.create(
            network_form.name,
            driver=network_form.networkDriver,
            ipam=ipam_config,
            options=network_options,
            internal=network_form.internal,
            enable_ipv6=network_form.ipv6_enabled,
            attachable=network_form.attachable,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=exc.response.status_code, detail=exc.explanation
        )

    return get_networks()


def get_network(network_id):
    dclient = docker.from_env()
    try:
        network = dclient.networks.get(network_id)
    except Exception as exc:
        raise HTTPException(
            status_code=exc.response.status_code, detail=exc.explanation
        )

    attrs = network.attrs
    net_id = attrs.get("Id")

    # Check if used
    containers = dclient.containers.list(all=True)
    in_use = False

    for container in containers:
        net_settings = container.attrs.get("NetworkSettings", {})
        nets = net_settings.get("Networks", {})
        for net_data in nets.values():
            if net_data.get("NetworkID") == net_id:
                in_use = True
                break
        if in_use:
            break

    attrs["inUse"] = in_use
    return attrs


def delete_network(network_id):
    dclient = docker.from_env()
    network = dclient.networks.get(network_id)
    try:
        network.remove()

    except Exception as exc:
        raise HTTPException(
            status_code=exc.response.status_code, detail=exc.explanation
        )

    return network.attrs


def prune_resources(resource):
    dclient = docker.from_env()
    action = getattr(dclient, resource)

    deleted_resource = None

    if resource == "images":
        # Docker SDK returns {'ImagesDeleted': [...], 'SpaceReclaimed': int}
        # If ImagesDeleted is None, it means no images were deleted.
        try:
            deleted_resource = action.prune(filters={"dangling": False})
        except Exception as e:
            # Fallback or error handling
            print(f"Error pruning images: {e}")
            return {"count": 0, "space_reclaimed": 0}

    else:
        # Other resources (containers, networks, volumes)
        try:
            deleted_resource = action.prune()
        except Exception as e:
            print(f"Error pruning {resource}: {e}")
            return {"count": 0, "space_reclaimed": 0}

    # If space is 0 or missing, ensure it is 0.
    if deleted_resource:
        if "SpaceReclaimed" not in deleted_resource:
            deleted_resource["SpaceReclaimed"] = 0

    return deleted_resource
