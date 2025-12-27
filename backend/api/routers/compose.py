from fastapi import APIRouter, Depends
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
from api.auth.auth import auth_check
from api.db.schemas import compose as schemas

router = APIRouter()


@router.get("/")
async def get_projects(Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return await get_compose_projects()


@router.get("/{project_name}")
async def get_project(project_name, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return await get_compose(project_name)


@router.get("/{project_name}/actions/{action}")
async def get_compose_action(project_name, action, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    if action == "delete":
        return await delete_compose(project_name)
    else:
        return await compose_action(project_name, action)


@router.post("/{project_name}/edit", response_model=schemas.ComposeRead)
async def write_compose_project(
    project_name, compose: schemas.ComposeWrite, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    return await write_compose(compose=compose)


@router.get("/{project_name}/actions/{action}/{app}")
async def get_compose_app_action(project_name, action, app, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return await compose_app_action(project_name, action, app)


@router.get("/{project_name}/support")
async def get_support_bundle(project_name, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return await generate_support_bundle(project_name)
