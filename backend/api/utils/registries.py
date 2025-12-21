from typing import List, Dict, Optional, Any
import httpx
import logging
import asyncio
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Cache structure
# {
#   'dockerhub': { 'data': [...], 'timestamp': ... },
#   'ghcr': { 'data': [...], 'timestamp': ... },
#   'linuxserver': { 'data': [...], 'timestamp': ... }
# }
REGISTRY_CACHE = {}
CACHE_DURATION = timedelta(minutes=30)

async def get_popular_images(registry: str) -> List[Dict]:
    """
    Get popular images for a specific registry.
    Uses caching.
    """
    now = datetime.now()
    if registry in REGISTRY_CACHE:
        cache_entry = REGISTRY_CACHE[registry]
        if now - cache_entry['timestamp'] < CACHE_DURATION:
            return cache_entry['data']

    data = []
    if registry == 'dockerhub':
        data = await fetch_dockerhub_popular()
    elif registry == 'ghcr':
        data = await fetch_ghcr_popular()
    elif registry == 'linuxserver':
        data = await fetch_linuxserver_popular()

    if data:
        REGISTRY_CACHE[registry] = {
            'data': data,
            'timestamp': now
        }

    return data

async def fetch_dockerhub_popular() -> List[Dict]:
    """
    Fetch popular images from Docker Hub (hardcoded popular list but fetched via API for details).
    """
    # From original code
    POPULAR_IMAGES = {
        "security": [
            "linuxserver/wireguard",
            "kylemanna/openvpn",
            "linuxserver/fail2ban",
            "linuxserver/authelia",
            "vaultwarden/server",
        ],
        "qol": [
            "linuxserver/heimdall",
            "portainer/portainer-ce",
            "netdata/netdata",
            "grafana/grafana",
            "prom/prometheus",
        ],
        "multimedia": [
            "linuxserver/plex",
            "linuxserver/jellyfin",
            "linuxserver/sonarr",
            "linuxserver/radarr",
            "linuxserver/lidarr",
        ],
        "stream": [
            "owncast/owncast",
            "blue-ocean/nginx-rtmp",
            "tiangolo/nginx-rtmp",
        ]
    }

    result = []
    async with httpx.AsyncClient() as client:
        # We can parallelize this
        tasks = []
        for category, images in POPULAR_IMAGES.items():
            for image_name in images:
                tasks.append(fetch_dockerhub_image_info(client, image_name))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, dict):
                result.append(res)
            elif isinstance(res, Exception):
                logger.error(f"Error fetching image: {res}")

    return result

async def fetch_dockerhub_image_info(client: httpx.AsyncClient, image_name: str) -> Optional[Dict]:
    try:
        url = f"https://hub.docker.com/v2/repositories/{image_name}"
        response = await client.get(url, timeout=10.0)
        if response.status_code == 200:
            data = response.json()
            return {
                "name": data.get("name"),
                "namespace": data.get("namespace"),
                "description": data.get("description", "")[:200],
                "pull_count": data.get("pull_count", 0),
                "star_count": data.get("star_count", 0),
                "is_official": data.get("is_official", False),
                "full_name": f"{data.get('namespace')}/{data.get('name')}",
                "logo_url": None, # Docker Hub API doesn't easily expose this publicly without auth sometimes
                "source": "dockerhub"
            }
    except Exception as e:
        logger.error(f"Error fetching {image_name}: {e}")
    return None

async def fetch_ghcr_popular() -> List[Dict]:
    """
    Fetch popular images from GitHub Container Registry.
    Since GHCR doesn't have a public 'popular' endpoint easily accessible without auth or searching users,
    we will use a hardcoded list of popular GHCR images as requested by user (e.g. linuxserver/plex).
    """
    # User mentioned: ghcr.io/linuxserver/plex, ghcr.io/homeassistant/home-assistant
    IMAGES = [
        "linuxserver/plex",
        "homeassistant/home-assistant",
        "linuxserver/radarr",
        "linuxserver/sonarr",
        "linuxserver/jellyfin"
    ]

    # GHCR API is different. It uses standard OCI distribution API or GitHub API.
    # We'll use GitHub API to get package info if possible.
    # https://api.github.com/users/{org}/packages/{package_type}/{package_name}

    result = []
    async with httpx.AsyncClient() as client:
        for image in IMAGES:
            try:
                # e.g. linuxserver/plex -> org: linuxserver, package: plex
                org, pkg = image.split('/')
                # Search for package
                # https://api.github.com/orgs/linuxserver/packages/container/plex
                url = f"https://api.github.com/orgs/{org}/packages/container/{pkg}"
                resp = await client.get(url, timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    result.append({
                        "name": data.get("name"),
                        "namespace": org,
                        "description": "GitHub Container Registry Package", # Description might not be in this endpoint
                        "pull_count": 0, # Not always available
                        "star_count": 0,
                        "is_official": False,
                        "full_name": f"ghcr.io/{image}",
                        "logo_url": "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png",
                        "source": "ghcr"
                    })
                else:
                    # Fallback if API fails (auth limits)
                     result.append({
                        "name": pkg,
                        "namespace": org,
                        "description": "GitHub Container Registry Image",
                        "pull_count": 0,
                        "star_count": 0,
                        "is_official": False,
                        "full_name": f"ghcr.io/{image}",
                        "logo_url": "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png",
                        "source": "ghcr"
                    })
            except Exception as e:
                logger.error(f"Error fetching GHCR {image}: {e}")

    return result

async def fetch_linuxserver_popular() -> List[Dict]:
    """
    Fetch from LinuxServer.io Fleet API.
    https://fleet.linuxserver.io/api/v1/images
    """
    url = "https://fleet.linuxserver.io/api/v1/images"
    result = []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                # data['data'] is list
                images = data.get('data', [])
                # Sort by pulls? They have 'pulls' field.
                images.sort(key=lambda x: x.get('pulls', 0), reverse=True)

                for img in images[:50]: # Top 50
                    # img structure: { "name": "plex", "github_user": "linuxserver", "pulls": 123, "stars": 123, "description": ... }
                    # Docker Hub image usually
                    repo = img.get('repository', {}).get('name') # e.g. linuxserver/plex
                    result.append({
                        "name": img.get('name'),
                        "namespace": "linuxserver",
                        "description": img.get('description', ""),
                        "pull_count": img.get('pulls', 0),
                        "star_count": img.get('stars', 0),
                        "is_official": False,
                        "full_name": repo or f"linuxserver/{img.get('name')}",
                        "logo_url": img.get('logo_url') or "https://www.linuxserver.io/img/logo.png",
                        "source": "linuxserver"
                    })
    except Exception as e:
        logger.error(f"Error fetching LSIO images: {e}")

    return result

async def search_registry(registry: str, query: str) -> List[Dict]:
    if not query:
        return []

    if registry == 'dockerhub':
        return await search_dockerhub(query)
    elif registry == 'ghcr':
        return await search_ghcr(query)
    elif registry == 'linuxserver':
        # Local filter of cached popular list + maybe fetch?
        # LSIO doesn't have a search API, but we can search the full list if we cache it?
        # For now, just search the popular list we fetched.
        popular = await get_popular_images('linuxserver')
        q = query.lower()
        return [img for img in popular if q in img['name'].lower() or q in img['description'].lower()]

    return []

async def search_dockerhub(query: str) -> List[Dict]:
    url = f"https://hub.docker.com/v2/search/repositories?query={query}&page_size=25"
    result = []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get('results', []):
                     result.append({
                        "name": item.get("name"),
                        "namespace": item.get("namespace"),
                        "description": item.get("description", "")[:200],
                        "pull_count": item.get("pull_count", 0),
                        "star_count": item.get("star_count", 0),
                        "is_official": item.get("is_official", False),
                        "full_name": f"{item.get('namespace')}/{item.get('name')}",
                        "logo_url": None,
                        "source": "dockerhub"
                    })
    except Exception as e:
        logger.error(f"Error searching Docker Hub: {e}")
    return result

async def search_ghcr(query: str) -> List[Dict]:
    # Strategy 1: Search User/Org packages
    # Strategy 2: Search Repositories with 'container' topic or description?

    result = []

    # 1. Try User/Org Packages
    try:
        async with httpx.AsyncClient() as client:
            url = f"https://api.github.com/users/{query}/packages?package_type=container"
            resp = await client.get(url, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                for item in data:
                     result.append({
                        "name": item.get("name"),
                        "namespace": item.get("owner", {}).get("login"),
                        "description": "GitHub Package",
                        "pull_count": 0,
                        "star_count": 0,
                        "is_official": False,
                        "full_name": f"ghcr.io/{item.get('owner', {}).get('login')}/{item.get('name')}",
                        "logo_url": "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png",
                        "source": "ghcr"
                    })
    except Exception as e:
        pass

    if result:
        return result

    # 2. Fallback: Search Repositories
    try:
        async with httpx.AsyncClient() as client:
            # Search repos matching query
            url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc"
            resp = await client.get(url, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get('items', [])[:10]:
                    full_name = item.get('full_name') # owner/repo
                    result.append({
                        "name": item.get("name"),
                        "namespace": item.get("owner", {}).get("login"),
                        "description": item.get("description", "")[:200],
                        "pull_count": 0,
                        "star_count": item.get("stargazers_count", 0),
                        "is_official": False,
                        "full_name": f"ghcr.io/{full_name}",
                        "logo_url": item.get("owner", {}).get("avatar_url") or "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png",
                        "source": "ghcr"
                    })
    except Exception as e:
        pass

    return result

async def get_image_tags(registry: str, image: str) -> List[str]:
    # image = namespace/repo (or full url)
    tags = []
    try:
        if registry == 'dockerhub' or registry == 'linuxserver':
             # For linuxserver, the image is often a Docker Hub repo (e.g. linuxserver/plex)
             # So we reuse Docker Hub logic.
             # https://hub.docker.com/v2/repositories/{namespace}/{repo}/tags
             if '/' not in image:
                 image = f"library/{image}"

             url = f"https://hub.docker.com/v2/repositories/{image}/tags?page_size=20"
             async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    tags = [t.get('name') for t in data.get('results', [])]

        elif registry == 'ghcr':
             # Need token for GHCR usually?
             # Use https://api.github.com/users/{org}/packages/container/{name}/versions
             if 'ghcr.io/' in image:
                 image = image.replace('ghcr.io/', '')
             parts = image.split('/')
             if len(parts) == 2:
                 org, name = parts
                 url = f"https://api.github.com/users/{org}/packages/container/{name}/versions"
                 async with httpx.AsyncClient() as client:
                    resp = await client.get(url, timeout=10.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        tags = [t.get('metadata', {}).get('container', {}).get('tags', []) for t in data]
                        # Flatten
                        flat_tags = []
                        for tlist in tags:
                            flat_tags.extend(tlist)
                        tags = list(set(flat_tags))
    except Exception as e:
        logger.error(f"Error fetching tags for {image}: {e}")

    return tags
