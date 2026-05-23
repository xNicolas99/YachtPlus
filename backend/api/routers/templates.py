from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from typing import List

from sqlalchemy.orm import Session

import api.db.crud.templates as crud
import api.db.crud.users as users_crud
import api.db.schemas.templates as schemas
from api.db.models.containers import Base
from api.db.database import engine
from api.utils.auth import get_db
from api.auth.auth import auth_check

from api.auth.jwt import get_auth_wrapper


router = APIRouter()


def _require_superuser(Authorize, db: Session) -> None:
    """Template add/delete/refresh fetches arbitrary URLs and mutates the
    template library, which is shared across all users — gate behind
    superuser like the user-management endpoints do.
    """
    auth_check(Authorize)
    username = Authorize.get_jwt_subject()
    if not username:
        raise HTTPException(status_code=401, detail="Not logged in.")
    user = users_crud.get_user_by_name(db=db, username=username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser required.")


@router.get(
    "/",
    response_model=List[schemas.TemplateRead],
)
def index(db: Session = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    templates = crud.get_templates(db=db)
    return templates


@router.get(
    "/match",
    response_model=List[schemas.TemplateItem],
)
def match(
    query: str,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    return crud.match_templates(db=db, query=query)


@router.get(
    "/{id}",
    response_model=schemas.TemplateItems,
)
def show(id: int, db: Session = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    template = crud.get_template_by_id(db=db, id=id)
    return template


@router.delete(
    "/{id}",
    response_model=schemas.TemplateRead,
)
def delete(id: int, db: Session = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    _require_superuser(Authorize, db)
    return crud.delete_template(db=db, template_id=id)


@router.post("/", response_model=schemas.TemplateRead)
def add_template(
    template: schemas.TemplateBase,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    _require_superuser(Authorize, db)
    existing_template = crud.get_template(db=db, url=template.url)
    if existing_template:
        raise HTTPException(status_code=400, detail="Template already in Database.")
    return crud.add_template(db=db, template=template)


@router.get(
    "/{id}/refresh",
    response_model=schemas.TemplateRead,
)
def refresh_template(
    id: int, db: Session = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    _require_superuser(Authorize, db)
    return crud.refresh_template(db=db, template_id=id)


@router.get(
    "/app/{id}",
    response_model=schemas.TemplateItem,
)
def read_app_template(
    id: int, db: Session = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    return crud.read_app_template(db=db, app_id=id)
