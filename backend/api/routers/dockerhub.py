import httpx
from fastapi import APIRouter, Query
from datetime import datetime, timedelta

router = APIRouter()

# Simple in-memory cache
_cache = {}
_cache_expiry = {}

async def fetch_docker_hub_repo(namespace: str, name: str):
    """
    Fetch real repository data from Docker Hub API.
    Caches the result for 1 hour to respect rate limits.
    """
    cache_key = f"{namespace}/{name}"

    # Check cache
    if cache_key in _cache and datetime.now() < _cache_expiry.get(cache_key, datetime.min):
        return _cache[cache_key]

    async with httpx.AsyncClient() as client:
        url = f"https://hub.docker.com/v2/repositories/{namespace}/{name}/"
        try:
            response = await client.get(url, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                _cache[cache_key] = data
                _cache_expiry[cache_key] = datetime.now() + timedelta(hours=1)
                return data
        except Exception as e:
            print(f"Error fetching Docker Hub data for {cache_key}: {e}")
            pass

    return None

@router.get("/popular")
async def get_popular_images():
    """
    Returns popular images with REAL data fetched from Docker Hub.
    """
    categories = {
        "security": ["nginxproxymanager/nginx-proxy-manager", "authelia/authelia", "linuxserver/swag"],
        "qol": ["portainer/portainer-ce", "containrrr/watchtower", "gethomepage/homepage"],
        "multimedia": ["plexinc/pms-docker", "jellyfin/jellyfin", "emby/embyserver"],
        "stream": ["obsproject/obs-studio", "owncast/owncast"]
    }

    results = {}

    for category, images in categories.items():
        results[category] = []
        for image_name in images:
            # Handle official images (library/) if necessary, though current list uses explicit namespaces
            if "/" not in image_name:
                namespace = "library"
                repo = image_name
            else:
                namespace, repo = image_name.split("/", 1)

            data = await fetch_docker_hub_repo(namespace, repo)

            if data:
                results[category].append({
                    "name": image_name,
                    "pulls": data.get("pull_count", 0),
                    "stars": data.get("star_count", 0),
                    "description": data.get("description", ""),
                    "is_official": data.get("is_official", False),
                    "last_updated": data.get("last_updated", "")
                })
            else:
                # Fallback if API fails
                results[category].append({
                    "name": image_name,
                    "pulls": 0,
                    "stars": 0,
                    "description": "Description unavailable (API Error)",
                    "is_official": False
                })

        # Sort by pull count descending
        results[category].sort(key=lambda x: x['pulls'], reverse=True)

    return results

@router.get("/search")
async def search_docker_hub(query: str = Query(..., min_length=2)):
    """
    Search Docker Hub repositories.
    """
    async with httpx.AsyncClient() as client:
        url = f"https://hub.docker.com/v2/search/repositories/"
        params = {
            "query": query,
            "page_size": 20
        }

        try:
            response = await client.get(url, params=params, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                return {
                    "results": [
                        {
                            "name": item.get("repo_name"),
                            "description": item.get("short_description", ""),
                            "pulls": item.get("pull_count", 0),
                            "stars": item.get("star_count", 0),
                            "is_official": item.get("is_official", False)
                        }
                        for item in data.get("results", [])
                    ]
                }
        except Exception as e:
             print(f"Docker Hub Search Error: {e}")

    return {"results": []}
