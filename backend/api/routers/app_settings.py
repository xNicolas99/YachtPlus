from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from typing import List
import io
import json

from sqlalchemy.ext.asyncio import AsyncSession

from api.utils.auth import get_db
from api.auth.auth import auth_check, require_superuser
from api.utils.security import limiter

from api.db.crud import templates as crud
from api.db.crud import settings as scrud
from api.db.schemas import templates as schemas

from api.actions import resources
from api.actions.apps import _update_self, check_self_update

from api.settings import Settings
from api.utils.deployment_mode import DeploymentMode, ConfigCheck

from api.auth.jwt import get_auth_wrapper


settings = Settings()

router = APIRouter()


@router.get(
    "/variables",
    response_model=List[schemas.TemplateVariables],
    operation_id="authorize",
)
async def read_template_variables(
    db: AsyncSession = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    return await crud.read_template_variables(db=db)


@router.post(
    "/variables",
    response_model=List[schemas.TemplateVariables],
)
async def set_template_variables(
    new_variables: List[schemas.TemplateVariables],
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    # Template variables substitute into every deploy — a non-admin who can
    # overwrite ${REGISTRY} or ${DOMAIN} can redirect future deploys to a
    # registry/host they control. Gate behind superuser.
    await require_superuser(Authorize, db)
    return await crud.set_template_variables(new_variables=new_variables, db=db)


@router.get(
    "/export",
    response_model=schemas.Import_Export,
)
async def export_settings(db: AsyncSession = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    await auth_check(Authorize)
    return await scrud.export_settings(db=db)


@router.post(
    "/export",
)
async def import_settings(
    db: AsyncSession = Depends(get_db),
    upload: UploadFile = File(...),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    # Settings import overwrites the whole settings table from an uploaded
    # JSON blob; any authenticated user could otherwise wipe the config of
    # the entire instance. Gate behind superuser.
    await require_superuser(Authorize, db)

    # Bound the upload BEFORE handing it to the CRUD layer:
    #  - content_type: reject anything that doesn't claim to be JSON so a
    #    user can't accidentally upload e.g. a 5 GB MP4.
    #  - size: cap at 5 MiB. A legit settings export is a few KB; anything
    #    larger is either a mistake or an OOM attempt against the worker
    #    that calls upload.file.read() unconditionally.
    #  - JSON well-formedness: parsing here gives a clean 400 instead of
    #    a 500 from inside the CRUD layer.
    MAX_IMPORT_BYTES = 5 * 1024 * 1024
    allowed_content_types = {"application/json", "text/json", "application/octet-stream"}
    ctype = (upload.content_type or "").lower().split(";")[0].strip()
    if ctype and ctype not in allowed_content_types:
        raise HTTPException(status_code=415, detail="Settings import must be application/json")

    import asyncio
    raw = await asyncio.to_thread(upload.file.read, MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Settings import exceeds {MAX_IMPORT_BYTES} bytes",
        )
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Settings import must be UTF-8 text")
    try:
        json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Settings import is not valid JSON")

    # Hand the CRUD layer a fresh file-like view so its `upload.file.read()`
    # call sees the same bytes we just validated (the original stream was
    # consumed by .read above).
    upload.file = io.BytesIO(raw)
    return await scrud.import_settings(db=db, upload=upload)


@router.get(
    "/prune/{resource}",
)
@limiter.limit("10/minute")
async def prune_resources(
    request: Request,
    resource: str,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    await require_superuser(Authorize, db)
    allowed = {"images", "containers", "volumes", "networks", "build_cache"}
    if resource not in allowed:
        raise HTTPException(
            status_code=422, detail=f"Resource must be one of {sorted(allowed)}"
        )
    return await resources.prune_resources(resource)


@router.get(
    "/update",
)
@limiter.limit("10/minute")
async def update_self(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    # Pulls + restarts the YachtPlus container itself. A non-admin able to
    # trigger this could force a denial-of-service via repeated restarts or
    # interrupt admin work mid-deploy. Restrict to superusers.
    await require_superuser(Authorize, db)
    return await _update_self(background_tasks)


@router.get(
    "/check/update",
)
async def _check_self_update(Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    await auth_check(Authorize)
    return await check_self_update()


@router.get("/deployment")
async def get_deployment_status(
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    """Read-only status of the detected deployment mode and config checks.

    Returns the mode (local/public/mixed) and the list of configuration
    health checks generated at startup. This endpoint is authenticated but
    not restricted to superusers — any authenticated operator may review
    the instance hardening status. (FND-501 / S7)
    """
    await auth_check(Authorize)
    mode = settings.MODE
    checks = settings.CONFIG_CHECKS
    return {
        "mode": mode.value,
        "checks": [
            {
                "rule_id": c.rule_id,
                "severity": c.severity.value,
                "message": c.message,
                "mode_expected": c.mode_expected.value if c.mode_expected else None,
                "config_keys": c.config_keys,
            }
            for c in checks
        ],
    }
