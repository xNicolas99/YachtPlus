from fastapi import APIRouter, Depends, status, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from api.db.schemas import apps as schemas
from api.db.crud import templates as template_crud
from api.db.database import SessionLocal
from sqlalchemy.orm import Session
import api.actions.apps as actions
from api.settings import Settings
from api.auth.auth import auth_check, check_permission
from api.utils.apps import calculate_cpu_percent, calculate_cpu_percent2, format_bytes, merge_template

from api.auth.jwt import get_auth_wrapper
import aiodocker
import json
import asyncio

settings = Settings()

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/")
def index(Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return actions.get_apps()


@router.get("/{app_name}/updates")
def check_app_updates(app_name, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return actions.check_app_update(app_name)


@router.get("/{app_name}/update")
def update_container(app_name, Authorize: get_auth_wrapper = Depends(get_auth_wrapper), db: Session = Depends(get_db)):
    auth_check(Authorize)
    check_permission("perm_restart", Authorize, db) # Update is effectively a restart/recreate
    return actions.app_update(app_name)

@router.get("/stats")
async def all_sse_stats(request: Request, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    stat_generator = actions.all_stat_generator(request)
    return EventSourceResponse(stat_generator)

@router.get("/{app_name}")
def get_container_details(app_name, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return actions.get_app(app_name=app_name)


@router.get("/{app_name}/processes", response_model=schemas.Processes)
def get_container_processes(app_name, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return actions.get_app_processes(app_name=app_name)


@router.get("/{app_name}/support")
def get_support_bundle(app_name, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return actions.generate_support_bundle(app_name)


@router.get("/actions/{app_name}/{action}")
def container_actions(app_name, action, background_tasks: BackgroundTasks, Authorize: get_auth_wrapper = Depends(get_auth_wrapper), db: Session = Depends(get_db)):
    auth_check(Authorize)
    if action == "start":
        check_permission("perm_start", Authorize, db)
    elif action == "stop":
        check_permission("perm_stop", Authorize, db)
    elif action == "restart":
        check_permission("perm_restart", Authorize, db)
    elif action == "kill" or action == "remove":
        check_permission("perm_delete", Authorize, db)

    return actions.app_action(app_name, action, background_tasks)

@router.post("/deploy", response_model=schemas.DeployLogs)
def deploy_app(template: schemas.DeployForm, Authorize: get_auth_wrapper = Depends(get_auth_wrapper), db: Session = Depends(get_db)):
    auth_check(Authorize)
    # Deploying implies starting/creating
    check_permission("perm_start", Authorize, db)

    # If template_id is provided, fetch defaults from DB and merge.
    if template.template_id:
        try:
            db_template_item = template_crud.read_app_template(db, template.template_id)
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

    result = actions.deploy_app(template=template)

    if isinstance(result, dict) and result.get("success") is False:
        return JSONResponse(status_code=409, content=result)

    return result

@router.get("/{app_name}/logs")
async def logs(app_name: str, request: Request, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    log_generator = actions.log_generator(request, app_name)
    return EventSourceResponse(log_generator)


@router.get("/{app_name}/stats")
async def sse_stats(app_name: str, request: Request, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    stat_generator = actions.stat_generator(request, app_name)
    return EventSourceResponse(stat_generator)
