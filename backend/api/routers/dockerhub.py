from fastapi import APIRouter
import httpx
from typing import List, Dict

router = APIRouter(prefix="/dockerhub", tags=["dockerhub"])

POPULAR_IMAGES = {
    "Security": [
        "linuxserver/wireguard",
        "kylemanna/openvpn",
        "linuxserver/fail2ban",
        "linuxserver/authelia",
        "vaultwarden/server",
    ],
    "QoL": [
        "linuxserver/heimdall",
        "portainer/portainer-ce",
        "netdata/netdata",
        "grafana/grafana",
        "prom/prometheus",
    ],
    "Multimedia": [
        "linuxserver/plex",
        "linuxserver/jellyfin",
        "linuxserver/sonarr",
        "linuxserver/radarr",
        "linuxserver/lidarr",
    ],
    "Stream": [
        "owncast/owncast",
        "blue-ocean/nginx-rtmp",
        "tiangolo/nginx-rtmp",
    ]
}

@router.get("/popular")
async def get_popular_images() -> Dict[str, List[Dict]]:
    result = {}
    async with httpx.AsyncClient() as client:
        for category, images in POPULAR_IMAGES.items():
            result[category] = []
            for image_name in images:
                try:
                    url = f"https://hub.docker.com/v2/repositories/{image_name}"
                    response = await client.get(url, timeout=5.0)
                    if response.status_code == 200:
                        data = response.json()
                        result[category].append({
                            "name": data.get("name"),
                            "namespace": data.get("namespace"),
                            "description": data.get("description", "")[:200],
                            "pull_count": data.get("pull_count", 0),
                            "star_count": data.get("star_count", 0),
                            "is_official": data.get("is_official", False),
                            "full_name": f"{data.get('namespace')}/{data.get('name')}",
                        })
                except Exception as e:
                    print(f"Error fetching {image_name}: {e}")
                    continue
    return result
