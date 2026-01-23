from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from api.db.database import get_db
from api.auth.auth import get_auth_wrapper
from api.utils import registries as registry_utils
from typing import List, Dict, Any

router = APIRouter()

# Removed strict response_model to prevent serialization crashes
@router.get("/", response_model=None)
async def get_registries(db: Session = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    Authorize.jwt_required()
    registries = registry_utils.get_registries(db)
    return registries

@router.get("/search")
async def search_registry(
    query: str,
    registry: str = Query("dockerhub", pattern="^(dockerhub|ghcr|linuxserver)$"),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    Authorize.jwt_required()
    return registry_utils.search_registry(query, registry)
