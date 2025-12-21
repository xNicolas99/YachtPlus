from fastapi import APIRouter, Depends, Query
from typing import List, Dict
from api.auth.jwt import get_auth_wrapper
from api.auth.auth import auth_check
import api.utils.registries as registries

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
