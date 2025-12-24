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

# Caching search results as well to avoid spamming external APIs on repeated queries
# Structure: { 'query_string': { 'registry': ..., 'data': [...], 'timestamp': ... } }
SEARCH_CACHE = {}
SEARCH_CACHE_DURATION = timedelta(minutes=5)

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
    Fetch popular images from Docker Hub.
    """
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
    # Use limits for concurrency to avoid blocking event loop or hitting rate limits too hard
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    async with httpx.AsyncClient(limits=limits) as client:
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
        response = await client.get(url, timeout=5.0) # Reduced timeout
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
                "logo_url": None,
                "source": "dockerhub",
                "last_updated": data.get("last_updated")
            }
    except Exception as e:
        logger.error(f"Error fetching {image_name}: {e}")
    return None

async def fetch_ghcr_popular() -> List[Dict]:
    """
    Fetch popular images from GitHub Container Registry.
    """
    IMAGES = [
        "linuxserver/plex",
        "homeassistant/home-assistant",
        "linuxserver/radarr",
        "linuxserver/sonarr",
        "linuxserver/jellyfin"
    ]

    result = []
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    async with httpx.AsyncClient(limits=limits) as client:
        for image in IMAGES:
            try:
                org, pkg = image.split('/')
                data = {}
                url = f"https://api.github.com/users/{org}/packages/container/{pkg}"
                try:
                    resp = await client.get(url, timeout=5.0)
                    if resp.status_code == 200:
                        data = resp.json()
                except:
                    pass

                result.append({
                    "name": data.get("name", pkg),
                    "namespace": org,
                    "description": "GitHub Container Registry Package",
                    "pull_count": 0,
                    "star_count": 0,
                    "is_official": False,
                    "full_name": f"ghcr.io/{image}",
                    "logo_url": "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png",
                    "source": "ghcr",
                    "last_updated": data.get("updated_at")
                })
            except Exception as e:
                logger.error(f"Error fetching GHCR {image}: {e}")

    return result

async def fetch_linuxserver_popular() -> List[Dict]:
    """
    Fetch from LinuxServer.io API.
    """
    urls = [
        "https://fleet.linuxserver.io/api/v1/images",
        "https://api.linuxserver.io/api/v1/images"
    ]

    result = []
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    async with httpx.AsyncClient(limits=limits) as client:
        for u in urls:
            try:
                resp = await client.get(u, timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    images = []
                    if 'data' in data and 'repositories' in data['data']:
                        images = data['data']['repositories'].get('linuxserver', [])
                    elif 'repositories' in data:
                         images = data['repositories'].get('linuxserver', [])

                    if not images:
                        continue

                    images.sort(key=lambda x: x.get('monthly_pulls', 0) or 0, reverse=True)

                    for img in images[:50]:
                        result.append({
                            "name": img.get('name'),
                            "namespace": "linuxserver",
                            "description": img.get('description', ""),
                            "pull_count": img.get('monthly_pulls', 0),
                            "star_count": img.get('stars', 0),
                            "is_official": False,
                            "full_name": f"linuxserver/{img.get('name')}",
                            "logo_url": img.get('project_logo') or "https://www.linuxserver.io/img/logo.png",
                            "source": "linuxserver",
                            "last_updated": img.get('version_timestamp'),
                            "github_url": img.get('github_url')
                        })
                    break
            except Exception as e:
                logger.error(f"Error fetching LSIO images from {u}: {e}")

    return result

async def search_registry(registry: str, query: str) -> List[Dict]:
    if not query:
        return []

    # Check Cache
    cache_key = f"{registry}:{query.lower()}"
    now = datetime.now()
    if cache_key in SEARCH_CACHE:
        entry = SEARCH_CACHE[cache_key]
        if now - entry['timestamp'] < SEARCH_CACHE_DURATION:
            return entry['data']

    result = []
    if registry == 'dockerhub':
        result = await search_dockerhub(query)
    elif registry == 'ghcr':
        result = await search_ghcr(query)
    elif registry == 'linuxserver':
        # Search popular list
        popular = await get_popular_images('linuxserver')
        q = query.lower()
        result = [img for img in popular if q in img['name'].lower() or q in img['description'].lower()]

    # Set Cache
    if result:
        SEARCH_CACHE[cache_key] = {
            'data': result,
            'timestamp': now
        }

    # Cleanup Old Cache (Naive implementation)
    if len(SEARCH_CACHE) > 100:
         keys_to_del = []
         for k, v in SEARCH_CACHE.items():
             if now - v['timestamp'] > SEARCH_CACHE_DURATION:
                 keys_to_del.append(k)
         for k in keys_to_del:
             del SEARCH_CACHE[k]

    return result

async def search_dockerhub(query: str) -> List[Dict]:
    url = f"https://hub.docker.com/v2/search/repositories?query={query}&page_size=25"
    result = []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get('results', []):
                    repo_name = item.get("repo_name")
                    if repo_name and '/' in repo_name:
                        namespace, name = repo_name.split('/', 1)
                    else:
                        namespace = "library"
                        name = repo_name

                    description = item.get("short_description") or "No description available."

                    result.append({
                        "name": name,
                        "namespace": namespace,
                        "description": description[:200],
                        "pull_count": item.get("pull_count", 0),
                        "star_count": item.get("star_count", 0),
                        "is_official": item.get("is_official", False),
                        "full_name": repo_name,
                        "logo_url": None,
                        "source": "dockerhub",
                        "last_updated": item.get("last_updated")
                    })
    except Exception as e:
        logger.error(f"Error searching Docker Hub: {e}")
    return result

async def search_ghcr(query: str) -> List[Dict]:
    result = []
    try:
        async with httpx.AsyncClient() as client:
            url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc"
            resp = await client.get(url, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get('items', [])[:20]:
                    full_name = item.get('full_name')
                    result.append({
                        "name": item.get("name"),
                        "namespace": item.get("owner", {}).get("login"),
                        "description": item.get("description", "")[:200],
                        "pull_count": 0,
                        "star_count": item.get("stargazers_count", 0),
                        "is_official": False,
                        "full_name": f"ghcr.io/{full_name}",
                        "logo_url": item.get("owner", {}).get("avatar_url") or "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png",
                        "source": "ghcr",
                        "last_updated": item.get("updated_at")
                    })
    except Exception as e:
        logger.error(f"Error searching GHCR: {e}")

    return result

async def get_image_tags(registry: str, image: str) -> List[str]:
    tags = []
    try:
        if registry == 'dockerhub' or registry == 'linuxserver':
             if '/' not in image:
                 image = f"library/{image}"

             if image.startswith('linuxserver/'):
                 pass

             url = f"https://hub.docker.com/v2/repositories/{image}/tags?page_size=20"
             async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    tags = [t.get('name') for t in data.get('results', [])]

        elif registry == 'ghcr':
             if 'ghcr.io/' in image:
                 image = image.replace('ghcr.io/', '')

             parts = image.split('/')
             if len(parts) >= 2:
                 org = parts[0]
                 pkg = parts[1]
                 url = f"https://api.github.com/users/{org}/packages/container/{pkg}/versions"
                 async with httpx.AsyncClient() as client:
                    resp = await client.get(url, timeout=10.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_tags = [t.get('metadata', {}).get('container', {}).get('tags', []) for t in data]
                        flat_tags = []
                        for tlist in raw_tags:
                            flat_tags.extend(tlist)
                        tags = list(set(flat_tags))
    except Exception as e:
        logger.error(f"Error fetching tags for {image}: {e}")

    return tags
