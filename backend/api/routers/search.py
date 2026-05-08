from fastapi import APIRouter, Depends
from typing import Dict, List, Any
from api.auth.jwt import get_auth_wrapper
from api.auth.auth import auth_check
from sqlalchemy.orm import Session
from api.utils.auth import get_db

import api.utils.registries as registries
from api.db.crud.templates import match_templates
from fastapi.concurrency import run_in_threadpool

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

    task_dockerhub = asyncio.create_task(registries.search_registry("dockerhub", q))

    # Await control back to the event loop just in case
    await asyncio.sleep(0)

    template_results_orm = await run_in_threadpool(match_templates, db, q)

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
