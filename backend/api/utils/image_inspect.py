import httpx
import logging
from typing import Dict, Optional

from api.utils.registry_helpers import get_registry_and_name

logger = logging.getLogger(__name__)


async def get_image_config(image_name: str) -> Optional[Dict]:
    """
    Fetches the image configuration (ExposedPorts, Volumes) from Docker Hub or GHCR.
    This is a best-effort implementation without authentication for public images.
    """
    registry, image_name = get_registry_and_name(image_name)

    if registry == "dockerhub":
        return await _get_dockerhub_config(image_name)

    # GHCR / linuxserver (lscr.io) support is more complex without auth token
    # for some endpoints, but we can try the public manifest endpoint if available.
    # For now, prioritize DockerHub as requested.
    return None


async def _get_dockerhub_config(image_name: str) -> Optional[Dict]:
    if "/" not in image_name:
        image_name = f"library/{image_name}"

    # Split tag before requesting the token: Docker Hub's token scope is
    # repository:<name>:pull, where <name> must NOT include a tag.
    tag = "latest"
    if ":" in image_name:
        image_name, tag = image_name.split(":", 1)

    # 1. Get Token
    auth_url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{image_name}:pull"
    async with httpx.AsyncClient() as client:
        try:
            auth_resp = await client.get(auth_url, timeout=5.0)
            if auth_resp.status_code != 200:
                return None
            token = auth_resp.json().get("token")

            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.docker.distribution.manifest.v2+json"
            }

            # 2. Get Manifest to find Config Blob Digest
            manifest_url = f"https://registry-1.docker.io/v2/{image_name}/manifests/{tag}"
            manifest_resp = await client.get(manifest_url, headers=headers, timeout=5.0)

            if manifest_resp.status_code != 200:
                return None

            manifest = manifest_resp.json()
            config_digest = manifest.get("config", {}).get("digest")

            if not config_digest:
                return None

            # 3. Get Config Blob
            blob_url = f"https://registry-1.docker.io/v2/{image_name}/blobs/{config_digest}"
            blob_resp = await client.get(blob_url, headers=headers, timeout=5.0)

            if blob_resp.status_code != 200:
                return None

            config = blob_resp.json()
            container_config = config.get("config", {}) or config.get("container_config", {})

            return {
                "ExposedPorts": container_config.get("ExposedPorts", {}),
                "Volumes": container_config.get("Volumes", {})
            }

        except Exception as e:
            logger.error(f"Error fetching config for {image_name}:{tag}: {e}")
            return None
