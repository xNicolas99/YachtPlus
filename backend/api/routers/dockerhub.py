from fastapi import APIRouter
from typing import Dict, List, Any

router = APIRouter()

POPULAR_IMAGES = {
    "security": [
        {"name": "nginxproxymanager/nginx-proxy-manager", "pulls": 100000000},
        {"name": "authelia/authelia", "pulls": 50000000},
        {"name": "linuxserver/swag", "pulls": 40000000},
        {"name": "fail2ban/fail2ban", "pulls": 10000000}, # Added one more for completeness
    ],
    "qol": [
        {"name": "portainer/portainer-ce", "pulls": 200000000},
        {"name": "containrrr/watchtower", "pulls": 80000000},
        {"name": "gethomepage/homepage", "pulls": 20000000},
        {"name": "louislam/uptime-kuma", "pulls": 50000000}, # Added popular QoL
    ],
    "multimedia": [
        {"name": "plexinc/pms-docker", "pulls": 150000000},
        {"name": "jellyfin/jellyfin", "pulls": 100000000},
        {"name": "emby/embyserver", "pulls": 50000000},
        {"name": "linuxserver/sonarr", "pulls": 75000000}, # Added popular media tool
        {"name": "linuxserver/radarr", "pulls": 70000000}, # Added popular media tool
    ],
    "stream": [
        {"name": "obsproject/obs-studio", "pulls": 30000000},
        {"name": "owncast/owncast", "pulls": 10000000},
        {"name": "datarhei/restreamer", "pulls": 5000000}, # Added from prompt example
    ]
}

@router.get("/popular")
async def get_popular_images() -> Dict[str, List[Dict[str, Any]]]:
    """
    Returns a list of popular Docker images categorized by type.
    """
    results = {}
    for category, images in POPULAR_IMAGES.items():
        results[category] = []
        for img in images:
            results[category].append(img)
    return results
