from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from api.db.database import get_db
from api.auth.auth import get_auth_wrapper
from api.utils import registries as registry_utils

router = APIRouter()

@router.get("/")
async def get_registries(db: Session = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    Authorize.jwt_required()
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
    Authorize.jwt_required()
    # Swapped arguments to match utils definition: search_registry(registry, query)
    return await registry_utils.search_registry(registry, query)
