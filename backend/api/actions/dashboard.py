from fastapi import HTTPException
import docker
from api.actions.compose import get_compose_projects

def get_dashboard_stats():
    """
    Aggregated stats for Dashboard cards.
    Bundles all information in a single request.
    """
    # Allow Docker exceptions to propagate to the global handler in main.py
    dclient = docker.from_env()
    containers = dclient.containers.list(all=True)
    images = dclient.images.list(all=True)
    volumes = dclient.volumes.list()
    networks = dclient.networks.list()

    # Parse compose projects
    try:
        projects = get_compose_projects()
    except Exception:
        projects = []

    # Containers Stats
    running_containers = [c for c in containers if c.status == "running"]
    stopped_containers = [c for c in containers if c.status in ["stopped", "exited"]]

    unhealthy_count = 0
    for c in containers:
        health = c.attrs.get("State", {}).get("Health", {}).get("Status")
        if health == "unhealthy":
            unhealthy_count += 1

    # Projects Stats
    active_projects = 0
    inactive_projects = 0
    for p in projects:
        # Implementation for Project Status:
        # We can cross-reference running containers with project name labels.
        # docker-compose usually adds label `com.docker.compose.project`.
        is_active = False
        for c in containers:
            labels = c.attrs.get("Config", {}).get("Labels", {})
            project_label = labels.get("com.docker.compose.project")
            if project_label == p["name"] and c.status == "running":
                is_active = True
                break

        if is_active:
            active_projects += 1
        else:
            inactive_projects += 1

    # Images Stats
    used_images_ids = set()
    for c in containers:
        img_id = c.attrs.get("Image")
        if img_id:
            used_images_ids.add(img_id)

    used_images_count = 0
    dangling_count = 0
    total_size = 0

    for i in images:
        total_size += i.attrs.get("Size", 0)
        if not i.tags:
            dangling_count += 1
        # Check if used
        if i.id in used_images_ids:
            used_images_count += 1
        else:
            # Also check tags match
                for tag in i.tags:
                    # Check if any container uses this tag
                    pass

    # Volumes Stats
    # "In Use: Volumes with at least 1 container mount"
    used_volumes = set()
    for c in containers:
        mounts = c.attrs.get("Mounts", [])
        for m in mounts:
            if m.get("Type") == "volume":
                used_volumes.add(m.get("Name"))

    in_use_volumes = 0
    for v in volumes:
        if v.name in used_volumes:
            in_use_volumes += 1

    # Networks Stats
    custom_networks = 0
    default_networks = 0
    default_names = ["bridge", "host", "none"]

    for n in networks:
        if n.name in default_names:
            default_networks += 1
        else:
            custom_networks += 1

    return {
        "containers": {
            "total": len(containers),
            "running": len(running_containers),
            "stopped": len(stopped_containers),
            "unhealthy": unhealthy_count
        },
        "projects": {
            "total": len(projects),
            "active": active_projects,
            "inactive": inactive_projects
        },
        "images": {
            "total": len(images),
            "used": used_images_count,
            "dangling": dangling_count,
            "total_size": total_size
        },
        "volumes": {
            "total": len(volumes),
            "in_use": in_use_volumes,
            "unused": len(volumes) - in_use_volumes
        },
        "networks": {
            "total": len(networks),
            "custom": custom_networks,
            "default": default_networks
        }
    }
