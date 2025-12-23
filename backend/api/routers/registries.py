from fastapi import APIRouter, Depends, Query
from typing import List, Dict, Optional
from api.auth.jwt import get_auth_wrapper
from api.auth.auth import auth_check
import api.utils.registries as registries
import api.utils.image_inspect as image_inspect

router = APIRouter(prefix="/registries", tags=["registries"])

@router.get("/popular")
async def get_popular(
    registry: str = Query("dockerhub", regex="^(dockerhub|ghcr|linuxserver)$"),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    return await registries.get_popular_images(registry)

@router.get("/search")
async def search(
    query: str,
    registry: str = Query("dockerhub", regex="^(dockerhub|ghcr|linuxserver)$"),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    return await registries.search_registry(registry, query)

@router.get("/tags")
async def get_tags(
    image: str,
    registry: str = Query("dockerhub", regex="^(dockerhub|ghcr|linuxserver)$"),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    return await registries.get_image_tags(registry, image)

@router.get("/inspect")
async def inspect_image(
    image: str,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    """
    Fetch remote image configuration (Ports, Volumes) from registry.
    """
    auth_check(Authorize)
    return await image_inspect.get_image_config(image)
