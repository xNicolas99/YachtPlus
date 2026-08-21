from fastapi import APIRouter, Depends, status, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio

from api.db.schemas import apps as schemas
from api.db.crud import templates as template_crud
from api.utils.auth import get_db
import api.actions.apps as actions
from api.settings import get_settings
settings = get_settings()
from api.auth.auth import auth_check, check_permission
from api.utils.apps import calculate_cpu_percent, calculate_cpu_percent2, format_bytes, merge_template
from api.utils.security import limiter
import api.db.crud.users as users_crud

from api.auth.jwt import get_auth_wrapper
from api.utils.audit import log_activity

import logging
import re as _re

logger = logging.getLogger(__name__)

# Docker container-name regex: must start alnum, then alnum/dot/dash/underscore.
_DEPLOY_NAME_RE = _re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")
# Network-mode strings the daemon actually accepts. Anything else (e.g.
# `container:<id-of-an-admin's-app>`) was sailing through unvalidated and
# would let a perm_start user attach their workload into another tenant's
# network namespace by name.
_DEPLOY_NETWORK_MODES = {"bridge", "host", "none", "default"}
# Capabilities that are permitted through the deploy form. Keep this an
# explicit whitelist: Docker adds new capabilities over time, and a
# blacklist will always lag behind.
_DEPLOY_ALLOWED_CAPS = {
    "CHOWN", "DAC_OVERRIDE", "FSETID", "FOWNER", "KILL", "SETGID",
    "SETUID", "SETPCAP", "NET_BIND_SERVICE", "SYS_CHROOT", "AUDIT_WRITE",
}


def _validate_deploy_template(template: "schemas.DeployForm") -> None:  # type: ignore[name-defined]
    """Defense-in-depth checks on the DeployForm before we hand it to the
    docker daemon. Pydantic only checks types — these are the
    semantic-validity rules. Failures map to 422 so the frontend can
    surface them as input validation errors instead of a 500.
    """
    if not _DEPLOY_NAME_RE.match(template.name or ""):
        raise HTTPException(status_code=422, detail="Invalid container name")

    image = (template.image or "").strip()
    # Block obvious shell-metacharacter smuggling through the image field
    # (image is forwarded to the docker daemon, but downstream tooling
    # sometimes echoes it into log lines or pulls scripts).
    if not image or any(ch in image for ch in (" ", "\n", "\r", "\t", ";", "|", "`", "$")):
        raise HTTPException(status_code=422, detail="Invalid image reference")
    if len(image) > 512:
        raise HTTPException(status_code=422, detail="Image reference too long")

    if template.network_mode is not None:
        mode = template.network_mode.strip()
        if mode and mode not in _DEPLOY_NETWORK_MODES:
            # `container:<id>` is technically valid but lets a perm_start
            # user jump into another tenant's netns; disallowed here.
            raise HTTPException(status_code=422, detail="Unsupported network_mode")

    if template.command:
        for i, part in enumerate(template.command):
            if not isinstance(part, str) or not part.strip():
                raise HTTPException(
                    status_code=422,
                    detail=f"command[{i}] must be a non-empty string",
                )
        cmd = [p.strip() for p in template.command]
        # Reject shell-style options that make the command field a remote
        # code execution channel. Only plain executable + arguments are
        # allowed; `-c` / `-e` / `--eval` and similar must be configured
        # in the image, not through the deploy form.
        if len(cmd) >= 2 and cmd[0] in ("sh", "bash", "ash", "zsh", "/bin/sh", "/bin/bash", "/bin/ash", "/bin/zsh"):
            if cmd[1] in ("-c", "--command"):
                raise HTTPException(
                    status_code=422,
                    detail="Shell command execution is not permitted through the deploy form",
                )
        if any(ch in ";|&`$()" for part in cmd for ch in part):
            raise HTTPException(
                status_code=422,
                detail="command contains disallowed shell metacharacters",
            )

    if template.cap_add:
        for cap in template.cap_add:
            cap_name = (cap or "").strip().upper().removeprefix("CAP_")
            if cap_name not in _DEPLOY_ALLOWED_CAPS:
                raise HTTPException(
                    status_code=422,
                    detail=f"Capability {cap_name} not permitted via deploy form",
                )

    # Volumes / devices: refuse bind-mounting docker.sock or anything
    # under /proc, /sys, /etc — a deploy with these would be equivalent
    # to handing out root on the host.
    sensitive_prefixes = ("/var/run/docker.sock", "/proc", "/sys", "/etc", "/root", "/boot")
    for vol in template.volumes or []:
        bind = (vol.bind or "").strip() if vol else ""
        if bind and any(bind == p or bind.startswith(p + "/") for p in sensitive_prefixes):
            raise HTTPException(
                status_code=422,
                detail="Volume bind path is restricted",
            )
    for dev in template.devices or []:
        host_path = (dev.host or "").strip() if dev else ""
        if host_path and any(host_path == p or host_path.startswith(p + "/") for p in sensitive_prefixes):
            raise HTTPException(
                status_code=422,
                detail="Device host path is restricted",
            )


async def _require_superuser(Authorize, db: AsyncSession) -> None:
    await auth_check(Authorize)
    username = await Authorize.get_jwt_subject()
    if not username:
        raise HTTPException(status_code=401, detail="Not logged in.")
    user = await users_crud.get_user_by_name(db=db, username=username)
    if not user or not user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser required.")


router = APIRouter()


@router.get("/")
async def index(Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    await auth_check(Authorize)
    return await actions.get_apps()


@router.get("/{app_name}/updates")
async def check_app_updates(app_name, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    await auth_check(Authorize)
    return await actions.check_app_update(app_name)


@router.post("/{app_name}/update")
async def update_container(app_name, Authorize: get_auth_wrapper = Depends(get_auth_wrapper), db: AsyncSession = Depends(get_db)):
    await auth_check(Authorize)
    await check_permission("perm_restart", Authorize, db) # Update is effectively a restart/recreate
    return await actions.app_update(app_name)

@router.get("/stats")
@limiter.limit("60/minute")
async def all_sse_stats(
    request: Request,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    db: AsyncSession = Depends(get_db),
):
    await auth_check(Authorize)
    await check_permission("perm_start", Authorize, db)
    stat_generator = actions.all_stat_generator(request)
    return EventSourceResponse(stat_generator)

@router.get("/{app_name}")
async def get_container_details(app_name, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    await auth_check(Authorize)
    return await actions.get_app(app_name=app_name)


@router.get("/{app_name}/processes", response_model=schemas.Processes)
async def get_container_processes(
    app_name,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    db: AsyncSession = Depends(get_db),
):
    # /proc-derived process listings expose command lines (often containing
    # secrets passed via flags). Gate behind perm_start so only operators
    # who can already control the container can read them.
    await auth_check(Authorize)
    await check_permission("perm_start", Authorize, db)
    return await actions.get_app_processes(app_name=app_name)


@router.get("/{app_name}/support")
async def get_support_bundle(
    app_name,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    db: AsyncSession = Depends(get_db),
):
    # Support bundles bundle env vars, config files and full container
    # inspect output — restrict to superusers.
    await _require_superuser(Authorize, db)
    return await actions.generate_support_bundle(app_name)


# POST is the correct verb — start/stop/kill/remove are state-changing and
# were CSRF-triggerable via GET (SameSite=lax sends the auth cookie on
@router.post("/actions/{app_name}/{action}")
async def container_actions(app_name, action, background_tasks: BackgroundTasks, Authorize: get_auth_wrapper = Depends(get_auth_wrapper), db: AsyncSession = Depends(get_db)):
    await auth_check(Authorize)

    # API keys are long-lived credentials. They remain valid for read-only
    # and low-risk automation, but container lifecycle mutations are too
    # dangerous to allow with a token that cannot be narrowed by scope today.
    # (FND-205 / S6)
    if Authorize.is_api_key():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API keys cannot perform container lifecycle actions"
        )

    if action == "start":
        await check_permission("perm_start", Authorize, db)
    elif action == "stop":
        await check_permission("perm_stop", Authorize, db)
    elif action == "restart":
        await check_permission("perm_restart", Authorize, db)
    elif action == "kill" or action == "remove":
        await check_permission("perm_delete", Authorize, db)

    # Audit Log
    try:
        user = await Authorize.get_jwt_subject()
        await log_activity(db, user, action, app_name)
    except Exception as e:
        # We deliberately don't block the action on audit-write failure
        # (an unavailable audit DB shouldn't lock operators out of the
        # platform), but the failure must reach the operator instead of
        # disappearing into stdout.
        logger.error(
            "Audit log write failed for action=%s resource=%s: %s",
            action, app_name, e, exc_info=True,
        )

    return await actions.app_action(app_name, action, background_tasks)

@router.post("/deploy", response_model=schemas.DeployLogs)
async def deploy_app(template: schemas.DeployForm, Authorize: get_auth_wrapper = Depends(get_auth_wrapper), db: AsyncSession = Depends(get_db)):
    await auth_check(Authorize)
    # Deploying implies starting/creating
    await check_permission("perm_start", Authorize, db)

    # If template_id is provided, fetch defaults from DB and merge.
    if template.template_id:
        try:
            db_template_item = await template_crud.read_app_template(db, template.template_id)
            if db_template_item:
                template = merge_template(template, db_template_item)
        except Exception as e:
            # If fetching template fails, we proceed with what we have, or log warning
            print(f"Error merging template: {e}")
            pass

    # Ensure required fields are present after merge
    if not template.image:
        raise HTTPException(status_code=422, detail="Image field is required and could not be determined from template.")
    if not template.name:
         raise HTTPException(status_code=422, detail="Name field is required.")

    _validate_deploy_template(template)

    result = await actions.deploy_app(template=template)

    if isinstance(result, dict) and result.get("success") is False:
        return JSONResponse(status_code=409, content=result)

    # Audit Log
    try:
        user = await Authorize.get_jwt_subject()
        await log_activity(db, user, "deploy", template.name, f"Image: {template.image}")
    except Exception as e:
        logger.error(
            "Audit log write failed for action=deploy resource=%s: %s",
            template.name, e, exc_info=True,
        )

    return result

@router.get("/{app_name}/logs")
async def logs(
    app_name: str,
    request: Request,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    db: AsyncSession = Depends(get_db),
):
    # Container stdout/stderr regularly contains secrets, tokens and
    # credentials printed during boot. Gate behind perm_start.
    await auth_check(Authorize)
    await check_permission("perm_start", Authorize, db)
    log_generator = actions.log_generator(request, app_name)
    return EventSourceResponse(log_generator)


@router.get("/{app_name}/stats")
@limiter.limit("60/minute")
async def sse_stats(
    app_name: str,
    request: Request,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    db: AsyncSession = Depends(get_db),
):
    await auth_check(Authorize)
    await check_permission("perm_start", Authorize, db)
    stat_generator = actions.stat_generator(request, app_name)
    return EventSourceResponse(stat_generator)
