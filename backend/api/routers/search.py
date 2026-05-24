from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Dict, List, Any
from api.auth.jwt import get_auth_wrapper
from api.auth.auth import auth_check
from sqlalchemy.orm import Session
from api.utils.auth import get_db
from slowapi import Limiter
from api.utils.security import rate_limit_key

import api.utils.registries as registries
from api.db.crud.templates import match_templates
from fastapi.concurrency import run_in_threadpool

import asyncio

router = APIRouter()

# Each search round-trips out to the DockerHub registry; without a rate
# limit a hostile (or just buggy) client could turn this endpoint into a
# free amplification proxy against the upstream registry, getting both
# the YachtPlus instance and its host IP throttled.
limiter = Limiter(key_func=rate_limit_key)

# Caps for the unified search:
#  - q max 128 chars: prevents huge LIKE patterns that pin the DB on a
#    full-table scan and keeps the DockerHub registry query bounded.
#  - q min 1 char: empty `q` would match every template row.
#  - max_results: hard ceiling on rows we serialize back so a tiny query
#    can't fan out into a megabyte response.
SEARCH_QUERY_MAX_LEN = 128
SEARCH_RESULT_LIMIT = 100


@router.get("/")
@limiter.limit("30/minute")
async def search(
    request: Request,
    q: str = Query(..., min_length=1, max_length=SEARCH_QUERY_MAX_LEN),
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
    for t in template_results_orm[:SEARCH_RESULT_LIMIT]:
        template_results.append({
            "id": t.id,
            "title": t.title,
            "name": t.name,
            "description": t.description,
            "image": t.image,
            "logo": t.logo,
            "url": t.url
        })

    if isinstance(dockerhub_results, list):
        dockerhub_results = dockerhub_results[:SEARCH_RESULT_LIMIT]

    return {
        "dockerhub": dockerhub_results,
        "templates": template_results
    }
