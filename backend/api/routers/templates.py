from __future__ import annotations
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from typing import List, Optional, Any
import json
import io
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

import api.db.crud.templates as crud
import api.db.crud.users as users_crud
import api.db.schemas.templates as schemas
from api.utils.auth import get_db
from api.auth.auth import auth_check

from api.auth.jwt import get_auth_wrapper

# Upper bound on uploaded / pasted catalog JSON — matches the existing
# settings-import cap, since the storage layer is the same SQLite DB
# and a giant payload would equally OOM the worker.
_TEMPLATE_PAYLOAD_MAX_BYTES = 5 * 1024 * 1024


router = APIRouter()


async def _require_superuser(Authorize, db: AsyncSession) -> None:
    """Template add/delete/refresh fetches arbitrary URLs and mutates the
    template library, which is shared across all users — gate behind
    superuser like the user-management endpoints do.
    """
    await auth_check(Authorize)
    username = await Authorize.get_jwt_subject()
    if not username:
        raise HTTPException(status_code=401, detail="Not logged in.")
    user = await users_crud.get_user_by_name(db=db, username=username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser required.")


@router.get(
    "/",
    response_model=List[schemas.TemplateRead],
)
async def index(db: AsyncSession = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    await auth_check(Authorize)
    templates = await crud.get_templates(db=db)
    return templates


@router.get(
    "/match",
    response_model=List[schemas.TemplateItem],
)
async def match(
    query: str,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    return await crud.match_templates(db=db, query=query)


@router.get(
    "/{id}",
    response_model=schemas.TemplateItems,
)
async def show(id: int, db: AsyncSession = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    await auth_check(Authorize)
    template = await crud.get_template_by_id(db=db, id=id)
    return template


@router.delete(
    "/{id}",
    response_model=schemas.TemplateRead,
)
async def delete(id: int, db: AsyncSession = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    await _require_superuser(Authorize, db)
    return await crud.delete_template(db=db, template_id=id)


@router.post("/", response_model=schemas.TemplateRead)
async def add_template(
    template: schemas.TemplateBase,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    await _require_superuser(Authorize, db)
    existing_template = await crud.get_template(db=db, url=template.url)
    if existing_template:
        raise HTTPException(status_code=400, detail="Template already in Database.")
    return await crud.add_template(db=db, template=template)


class ManualTemplateBody(BaseModel):
    title: str
    # Either a list[dict] (Portainer-v2 format — the common shape) or a
    # single dict for a one-entry catalog. Frontend usually sends a list.
    content: Any


class EditTemplateBody(BaseModel):
    title: Optional[str] = None
    content: Any


def _parse_uploaded_json(raw: bytes):
    """Validate + decode an uploaded JSON catalog. Bounded and explicit
    about the failure modes so the user gets a 422 for "you uploaded a
    YAML" instead of a 500."""
    if len(raw) > _TEMPLATE_PAYLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Template upload exceeds {_TEMPLATE_PAYLOAD_MAX_BYTES} bytes",
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Catalog must be UTF-8 text")
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        raise HTTPException(
            status_code=400, detail=f"Catalog is not valid JSON: {err.msg} (line {err.lineno})"
        )


@router.post("/upload", response_model=schemas.TemplateRead)
async def upload_template(
    # `title` MUST be annotated as a query param. Without the explicit
    # Query(...) tag FastAPI, on a route that has `File(...)`, treats
    # every other primitive param as Form data — and the frontend sends
    # the title as `?title=…`, so the request 422'd before my code ever
    # ran. From the user's POV the Upload dialog "did nothing".
    title: str = Query(..., min_length=1, max_length=255),
    upload: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    await _require_superuser(Authorize, db)
    ctype = (upload.content_type or "").lower().split(";")[0].strip()
    if ctype and ctype not in ("application/json", "text/json", "application/octet-stream", "text/plain"):
        raise HTTPException(status_code=415, detail="Upload must be application/json")

    raw = await asyncio.to_thread(upload.file.read, _TEMPLATE_PAYLOAD_MAX_BYTES + 1)
    payload = _parse_uploaded_json(raw)
    return await crud.add_template_from_payload(db=db, title=title, payload=payload)


@router.post("/manual", response_model=schemas.TemplateRead)
async def create_manual_template(
    body: ManualTemplateBody,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    await _require_superuser(Authorize, db)
    return await crud.add_template_from_payload(db=db, title=body.title, payload=body.content)


@router.put("/{id}/content", response_model=schemas.TemplateRead)
async def edit_template_content(
    id: int,
    body: EditTemplateBody,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    await _require_superuser(Authorize, db)
    return await crud.replace_template_items(
        db=db, template_id=id, payload=body.content, title=body.title,
    )


@router.get(
    "/{id}/refresh",
    response_model=schemas.TemplateRead,
)
async def refresh_template(
    id: int, db: AsyncSession = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await _require_superuser(Authorize, db)
    return await crud.refresh_template(db=db, template_id=id)


@router.get(
    "/app/{id}",
    response_model=schemas.TemplateItem,
)
async def read_app_template(
    id: int, db: AsyncSession = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    return await crud.read_app_template(db=db, app_id=id)
