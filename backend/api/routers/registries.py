from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from api.db.database import get_db
from api.auth.jwt import get_auth_wrapper
from api.utils import registries as registry_utils

router = APIRouter()

@router.get("/")
async def get_registries(db: AsyncSession = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    await Authorize.jwt_required()
    # Returns a list of supported registries.
    # This replaces the missing registry_utils.get_registries(db)
    return [
        {"name": "Docker Hub", "url": "https://hub.docker.com", "icon": "mdi-docker", "id": "dockerhub"},
        {"name": "GitHub (GHCR)", "url": "ghcr.io", "icon": "mdi-github", "id": "ghcr"},
        {"name": "LinuxServer.io", "url": "https://linuxserver.io", "icon": "mdi-linux", "id": "linuxserver"}
    ]

@router.get("/search")
async def search_registry(
    query: str,
    registry: str = Query("dockerhub", pattern="^(dockerhub|ghcr|linuxserver)$"),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await Authorize.jwt_required()
    # Swapped arguments to match utils definition: search_registry(registry, query)
    return await registry_utils.search_registry(registry, query)


# The Templates -> "Docker Hub Popular" tab in the frontend calls
# /registries/popular and /registries/tags. The util functions existed
# (get_popular_images, get_image_tags) but no router exposed them, so
# every load of the page produced a wall of 404s and the curated catalog
# never appeared. /inspect rounds it out for ApplicationsForm.vue which
# probes an image for its default ports/env before opening the deploy
# dialog.

@router.get("/popular")
async def popular_images(
    registry: str = Query("dockerhub", pattern="^(dockerhub|ghcr|linuxserver)$"),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    await Authorize.jwt_required()
    return await registry_utils.get_popular_images(registry)


@router.get("/tags")
async def image_tags(
    image: str,
    registry: str = Query("dockerhub", pattern="^(dockerhub|ghcr|linuxserver)$"),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    await Authorize.jwt_required()
    if not image or not image.strip():
        return []
    return await registry_utils.get_image_tags(registry, image.strip())


@router.get("/inspect")
async def inspect_image(
    image: str,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    """Best-effort metadata lookup for an image (mainly DockerHub's
    `short_description` / `description`). The deploy form uses this
    to pre-fill a notes field. Returns an empty dict if the registry
    couldn't be reached or the image is unknown — never a 500.
    """
    await Authorize.jwt_required()
    if not image or not image.strip():
        return {}
    image = image.strip()
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            return await registry_utils.fetch_dockerhub_image_info(client, image) or {}
    except Exception:
        return {}
