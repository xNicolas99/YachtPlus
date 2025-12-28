from fastapi import APIRouter, Depends
from typing import Dict, List, Any
from api.auth.jwt import get_auth_wrapper
from api.auth.auth import auth_check
from sqlalchemy.orm import Session
from api.utils.auth import get_db

import api.utils.registries as registries
from api.db.crud.templates import match_templates

import asyncio

router = APIRouter()

@router.get("/")
async def search(
    q: str,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    """
    Unified search endpoint.
    Searches DockerHub and Templates (and potentially others).
    """
    auth_check(Authorize)

    # Run searches in parallel
    # Note: match_templates is synchronous (DB call), registries.search is async

    # Create tasks
    # 1. DockerHub (Async)
    task_dockerhub = registries.search_registry("dockerhub", q)

    # 2. Templates (Sync - wrap in thread or just run)
    # Since it's a DB call, it's blocking. For optimal performance we could use run_in_executor
    # But usually it's fast. Let's just call it.
    # Wait, we can't run sync function in gather easily without to_thread.
    # Let's run async first, then sync.

    dockerhub_results = await task_dockerhub

    # Templates
    template_results_orm = match_templates(db, q)
    # Convert ORM objects to dicts or Pydantic models
    template_results = []
    for t in template_results_orm:
        template_results.append({
            "id": t.id,
            "title": t.title,
            "name": t.name,
            "description": t.description,
            "image": t.image,
            "logo": t.logo,
            "url": t.url
        })

    return {
        "dockerhub": dockerhub_results,
        "templates": template_results
    }
