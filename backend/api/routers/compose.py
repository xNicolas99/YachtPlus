from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.auth.jwt import get_auth_wrapper

from api.actions.compose import (
    get_compose_projects,
    compose_action,
    compose_app_action,
    get_compose,
    write_compose,
    delete_compose,
    generate_support_bundle,
)
from api.auth.auth import auth_check, check_permission
from api.utils.auth import get_db
from api.db.schemas import compose as schemas
import api.db.crud.users as users_crud


def _require_superuser(Authorize, db: Session) -> None:
    auth_check(Authorize)
    username = Authorize.get_jwt_subject()
    if not username:
        raise HTTPException(status_code=401, detail="Not logged in.")
    user = users_crud.get_user_by_name(db=db, username=username)
    if not user or not user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser required.")

router = APIRouter()


# Maps compose router action verbs to the user permission flags already
# enforced on the apps router. Verbs not in this mapping (e.g. "pull")
# fall back to auth_check only.
_ACTION_PERMISSIONS = {
    "up": "perm_start",
    "create": "perm_start",
    "start": "perm_start",
    "stop": "perm_stop",
    "down": "perm_stop",
    "restart": "perm_restart",
    "delete": "perm_delete",
    "rm": "perm_delete",
}


def _require_action_permission(action: str, Authorize, db):
    perm = _ACTION_PERMISSIONS.get(action)
    if perm:
        check_permission(perm, Authorize, db)


@router.get("/")
async def get_projects(
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    db: Session = Depends(get_db),
):
    # The listing exposes project names + paths; gate behind perm_start
    # so a read-only-account user can't enumerate stack layouts. (perm_start
    # is the lowest "operator" privilege already required to do anything
    # with a project.)
    auth_check(Authorize)
    check_permission("perm_start", Authorize, db)
    return await get_compose_projects()


@router.get("/{project_name}")
async def get_project(
    project_name,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    db: Session = Depends(get_db),
):
    # Project detail returns the raw compose YAML which routinely contains
    # secrets (DB passwords, API keys, OIDC client secrets) as `environment`
    # values. Restrict to superusers — perm_start operators can run actions
    # but should not get a free dump of every stack's secrets.
    _require_superuser(Authorize, db)
    return await get_compose(project_name)


@router.get("/{project_name}/actions/{action}")
async def get_compose_action(
    project_name,
    action,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    db: Session = Depends(get_db),
):
    auth_check(Authorize)
    if action not in ["up", "down", "start", "stop", "restart", "create", "delete", "pull"]:
        raise HTTPException(status_code=400, detail="Invalid action")
    _require_action_permission(action, Authorize, db)
    if action == "delete":
        return await delete_compose(project_name)
    else:
        return await compose_action(project_name, action)


@router.post("/{project_name}/edit", response_model=schemas.ComposeRead)
async def write_compose_project(
    project_name,
    compose: schemas.ComposeWrite,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    db: Session = Depends(get_db),
):
    auth_check(Authorize)
    # Editing a compose file changes how the stack runs on next deploy,
    # so gate it behind the same permission used for restarts.
    check_permission("perm_restart", Authorize, db)
    return await write_compose(compose=compose)


@router.get("/{project_name}/actions/{action}/{app}")
async def get_compose_app_action(
    project_name,
    action,
    app,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    db: Session = Depends(get_db),
):
    auth_check(Authorize)
    if action not in ["up", "down", "start", "stop", "restart", "create", "rm", "pull"]:
        raise HTTPException(status_code=400, detail="Invalid action")
    _require_action_permission(action, Authorize, db)
    return await compose_app_action(project_name, action, app)


@router.get("/{project_name}/support")
async def get_support_bundle(
    project_name,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    db: Session = Depends(get_db),
):
    # Support bundles include compose files, env values, and stack-wide
    # config that often contains secrets. Restrict to superusers.
    _require_superuser(Authorize, db)
    return await generate_support_bundle(project_name)
