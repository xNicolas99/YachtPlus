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
    # Schedule the network request to run concurrently in the background
    task_dockerhub = asyncio.create_task(registries.search_registry("dockerhub", q))

    # 2. Templates (Sync - wrap in thread or just run)
    # Since it's a DB call, it's blocking. For optimal performance we could use run_in_executor
    # But usually it's fast. Let's just call it.

    # Yield control back to the event loop so task_dockerhub can actually begin executing
    # the network I/O before we block the thread with our synchronous database query.
    await asyncio.sleep(0)

    # Execute synchronous database query (CPU/Disk blocking)
    template_results_orm = match_templates(db, q)

    # Await the completion of the background network task
    dockerhub_results = await task_dockerhub
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
