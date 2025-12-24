from fastapi import HTTPException
import aiodocker
import asyncio
import logging
from api.utils.compose import find_yml_files
from api.settings import Settings

settings = Settings()
logger = logging.getLogger(__name__)

async def get_dashboard_stats():
    """
    Aggregated stats for Dashboard cards.
    Bundles all information in a single request.
    Optimized for performance:
    - Async parallel fetching of Docker resources
    - Avoids parsing YAML for compose projects (only lists files)
    - Robust error handling for partial failures
    """

    try:
        async with aiodocker.Docker() as docker:
            containers_task = docker.containers.list(all=True)
            images_task = docker.images.list()
            volumes_task = docker.volumes.list()
            networks_task = docker.networks.list()

            results = await asyncio.gather(
                containers_task, images_task, volumes_task, networks_task,
                return_exceptions=True
            )

            # Unpack results, handling exceptions for each task
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

            if isinstance(results[2], Exception):
                logger.error(f"Error fetching volumes: {results[2]}")
                volumes_data = {}
            else:
                volumes_data = results[2]

            if isinstance(results[3], Exception):
                logger.error(f"Error fetching networks: {results[3]}")
                networks = []
            else:
                networks = results[3]

            volumes = volumes_data.get('Volumes', []) or []
    except Exception as e:
        logger.error(f"Critical error connecting to Docker in get_dashboard_stats: {e}")
        # Return empty stats structure to prevent frontend crash
        return {
            "containers": {"total": 0, "running": 0, "stopped": 0, "unhealthy": 0},
            "projects": {"total": 0, "active": 0, "inactive": 0},
            "images": {"total": 0, "used": 0, "dangling": 0, "total_size": 0},
            "volumes": {"total": 0, "in_use": 0, "unused": 0},
            "networks": {"total": 0, "custom": 0, "default": 0}
        }

    try:
        loop = asyncio.get_event_loop()
        project_files = await loop.run_in_executor(None, find_yml_files, settings.COMPOSE_DIR)
        project_names = set(project_files.keys()) if project_files else set()
    except Exception as e:
        logger.error(f"Error finding compose files: {e}")
        project_names = set()

    running_count = 0
    stopped_count = 0
    unhealthy_count = 0

    active_projects = set()

    used_images_ids = set()
    used_volumes = set()

    for c in containers:
        # aiodocker.Docker().containers.list() returns DockerContainer objects
        # accessing _container attribute gives the dict,
        # BUT aiodocker 0.21.0 might return dicts if list() is called?
        # Actually in api/actions/apps.py it assumes 'app' is an object and accesses 'app._container'.
        # So we should handle both or normalize.

        c_dict = c._container if hasattr(c, '_container') else c

        if not isinstance(c_dict, dict):
            continue

        state = c_dict.get('State', 'stopped')

        if state == 'running':
            running_count += 1

            labels = c_dict.get('Labels') or {}
            project_label = labels.get("com.docker.compose.project")
            if project_label and project_label in project_names:
                active_projects.add(project_label)

        elif state in ['exited', 'stopped', 'dead']:
             stopped_count += 1

        status_str = c_dict.get("Status", "")
        if "(unhealthy)" in status_str:
            unhealthy_count += 1

        img_id = c_dict.get('ImageID')
        if img_id:
            used_images_ids.add(img_id)

        mounts = c_dict.get('Mounts', [])
        for m in mounts:
            if m.get('Type') == 'volume':
                name = m.get('Name')
                if name:
                    used_volumes.add(name)

    total_projects = len(project_names)
    active_projects_count = len(active_projects)
    inactive_projects_count = total_projects - active_projects_count

    used_images_count = 0
    dangling_count = 0
    total_size = 0

    for i in images:
        if not isinstance(i, dict):
            continue

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
        if not isinstance(n, dict):
            continue

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
