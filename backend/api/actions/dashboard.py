import aiodocker
import asyncio
import logging
import os
import shutil
import psutil
from api.utils.compose import find_yml_files
from api.settings import get_settings
settings = get_settings()

logger = logging.getLogger(__name__)


def _read_cgroup_memory_stats() -> dict:
    """Return container memory limit/usage from cgroup when available.

    Inside a Docker container, psutil.virtual_memory() reports the *host*
    memory, which is misleading for the dashboard KPI strip. cgroup v1 and
    v2 expose the container's actual limit and usage under /sys/fs/cgroup.
    If the files are missing (e.g. running outside a container) we fall
    back to psutil below.

    Returns a dict with optional keys: limit, usage. Missing keys mean
    cgroup data is not available.
    """
    result: dict = {}

    # cgroup v2 unified hierarchy
    cgroup_v2_usage = "/sys/fs/cgroup/memory.current"
    cgroup_v2_limit = "/sys/fs/cgroup/memory.max"
    if os.path.exists(cgroup_v2_usage) and os.path.exists(cgroup_v2_limit):
        try:
            with open(cgroup_v2_usage, "r") as f:
                result["usage"] = int(f.read().strip())
            with open(cgroup_v2_limit, "r") as f:
                limit_raw = f.read().strip()
                # "max" means no limit
                result["limit"] = int(limit_raw) if limit_raw.isdigit() else 0
        except Exception as e:
            logger.debug("Could not read cgroup v2 memory files: %s", e)
        return result

    # cgroup v1
    cgroup_v1_limit = "/sys/fs/cgroup/memory/memory.limit_in_bytes"
    cgroup_v1_usage = "/sys/fs/cgroup/memory/memory.usage_in_bytes"
    if os.path.exists(cgroup_v1_limit) and os.path.exists(cgroup_v1_usage):
        try:
            with open(cgroup_v1_limit, "r") as f:
                result["limit"] = int(f.read().strip())
            with open(cgroup_v1_usage, "r") as f:
                result["usage"] = int(f.read().strip())
        except Exception as e:
            logger.debug("Could not read cgroup v1 memory files: %s", e)
        return result

    return result


async def _get_container_memory() -> dict:
    """Return memory stats, preferring cgroup container limits over host RAM."""
    cgroup = await asyncio.to_thread(_read_cgroup_memory_stats)

    if cgroup.get("limit") and cgroup.get("limit") > 0:
        limit = cgroup["limit"]
        usage = cgroup.get("usage", 0)
        percent = round((usage / limit) * 100, 1) if limit else 0
        return {
            "ram": percent,
            "ram_total": limit,
            "ram_used": usage,
            "source": "cgroup",
        }

    # Fallback to psutil (host view, but still useful outside containers).
    mem = await asyncio.to_thread(psutil.virtual_memory)
    return {
        "ram": mem.percent,
        "ram_total": mem.total,
        "ram_used": mem.used,
        "source": "psutil",
    }


async def get_dashboard_stats():
    """
    Aggregated stats for Dashboard cards.
    Bundles all information in a single request.
    Optimized for performance:
    - Async parallel fetching of Docker resources
    - Avoids parsing YAML for compose projects (only lists files)
    - Robust error handling for partial failures
    """

    # Initialize empty structures
    containers = []
    images = []
    volumes = []
    networks = []

    # System Resources
    try:
        cpu_percent = await asyncio.to_thread(psutil.cpu_percent)
        mem_stats = await _get_container_memory()
        resources = {
            "cpu": cpu_percent,
            **mem_stats,
        }
    except Exception as e:
        logger.error(f"Error fetching system resources: {e}")
        resources = {
            "cpu": 0,
            "ram": 0,
            "ram_total": 0,
            "ram_used": 0,
        }

    # Increase timeout for Docker stats collection
    # We split this into two parts: Critical (Containers) and Secondary (Images, Volumes, Networks)
    # If Secondary fails, we still return Containers.

    async with aiodocker.Docker(url=get_settings().DOCKER_HOST) as docker:
        # Part 1: Critical - Containers
        try:
             # 5s timeout for containers
             containers = await asyncio.wait_for(
                 docker.containers.list(all=True),
                 timeout=5.0
             )
        except Exception as e:
            logger.error(f"Error fetching containers: {e}")
            # If containers fail, we probably can't do much, but we return empty to avoid 500
            return {
                "containers": {"total": 0, "running": 0, "stopped": 0, "unhealthy": 0},
                "projects": {"total": 0, "active": 0, "inactive": 0},
                "images": {"total": 0, "used": 0, "dangling": 0, "total_size": 0},
                "volumes": {"total": 0, "in_use": 0, "unused": 0},
                "networks": {"total": 0, "custom": 0, "default": 0},
                "resources": resources
            }

        # Part 2: Secondary - Images, Volumes, Networks
        # We run them in parallel but catch individual errors
        async def fetch_safe(coro, default):
            try:
                return await asyncio.wait_for(coro, timeout=5.0)
            except Exception as e:
                logger.warning(f"Stats fetch failed for {default}: {e}")
                return default

        results = await asyncio.gather(
            fetch_safe(docker.images.list(), []),
            fetch_safe(docker.volumes.list(), {}),
            fetch_safe(docker.networks.list(), []),
            return_exceptions=True
        )

        # Unpack results
        images = results[0] if isinstance(results[0], list) else []
        volumes_data = results[1] if isinstance(results[1], dict) else {}
        networks = results[2] if isinstance(results[2], list) else []

        volumes = volumes_data.get('Volumes', []) or []

    try:
        loop = asyncio.get_event_loop()
        project_files = await loop.run_in_executor(None, find_yml_files, get_settings().COMPOSE_DIR)
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
        },
        "resources": resources
    }
