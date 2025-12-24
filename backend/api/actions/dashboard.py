from fastapi import HTTPException
import aiodocker
import asyncio
from api.utils.compose import find_yml_files
from api.settings import Settings

settings = Settings()

async def get_dashboard_stats():
    """
    Aggregated stats for Dashboard cards.
    Bundles all information in a single request.
    Optimized for performance:
    - Async parallel fetching of Docker resources
    - Avoids parsing YAML for compose projects (only lists files)
    """

    async with aiodocker.Docker() as docker:
        containers_task = docker.containers.list(all=True)
        images_task = docker.images.list()
        volumes_task = docker.volumes.list()
        networks_task = docker.networks.list()

        try:
            containers, images, volumes_data, networks = await asyncio.gather(
                containers_task, images_task, volumes_task, networks_task
            )
        except Exception as exc:
             raise HTTPException(status_code=503, detail=f"Docker connection error: {exc}")

        volumes = volumes_data.get('Volumes', []) or []

    try:
        loop = asyncio.get_event_loop()
        project_files = await loop.run_in_executor(None, find_yml_files, settings.COMPOSE_DIR)
        project_names = set(project_files.keys())
    except Exception:
        project_names = set()

    running_count = 0
    stopped_count = 0
    unhealthy_count = 0

    active_projects = set()

    used_images_ids = set()
    used_volumes = set()

    for c in containers:
        state = c.get('State', 'stopped')

        if state == 'running':
            running_count += 1

            labels = c.get('Labels', {})
            project_label = labels.get("com.docker.compose.project")
            if project_label and project_label in project_names:
                active_projects.add(project_label)

        elif state in ['exited', 'stopped', 'dead']:
             stopped_count += 1

        status_str = c.get("Status", "")
        if "(unhealthy)" in status_str:
            unhealthy_count += 1

        img_id = c.get('ImageID')
        if img_id:
            used_images_ids.add(img_id)

        mounts = c.get('Mounts', [])
        for m in mounts:
            if m.get('Type') == 'volume':
                used_volumes.add(m.get('Name'))

    total_projects = len(project_names)
    active_projects_count = len(active_projects)
    inactive_projects_count = total_projects - active_projects_count

    used_images_count = 0
    dangling_count = 0
    total_size = 0

    for i in images:
        total_size += i.get("Size", 0)
        repo_tags = i.get("RepoTags")
        if not repo_tags or repo_tags == ["<none>:<none>"]:
            dangling_count += 1

        if i.get('Id') in used_images_ids:
            used_images_count += 1

    in_use_volumes = 0
    for v in volumes:
        if v.get('Name') in used_volumes:
            in_use_volumes += 1

    custom_networks = 0
    default_networks = 0
    default_names = {"bridge", "host", "none"}

    for n in networks:
        if n.get('Name') in default_names:
            default_networks += 1
        else:
            custom_networks += 1

    return {
        "containers": {
            "total": len(containers),
            "running": running_count,
            "stopped": stopped_count,
            "unhealthy": unhealthy_count
        },
        "projects": {
            "total": total_projects,
            "active": active_projects_count,
            "inactive": inactive_projects_count
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
