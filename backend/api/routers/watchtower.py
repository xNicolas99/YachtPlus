from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from api.auth.jwt import get_auth_wrapper
from api.auth.auth import auth_check, require_superuser
from api.services.watchtower import update_compose_project, update_all_projects
from api.utils.auth import get_db
from api.utils.compose import validate_compose_project_name, find_yml_files
from api.actions.compose import run_in_thread
from api.settings import get_settings

router = APIRouter()

@router.post("/update/{project_name}")
async def trigger_project_update(
    project_name: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    # Watchtower-style updates pull new images and restart compose
    # projects host-wide. A non-admin able to trigger this could time
    # forced restarts to break in-flight work or burn bandwidth.
    await require_superuser(Authorize, db)
    validate_compose_project_name(project_name)
    await run_in_thread(update_compose_project, project_name)
    return {"message": f"Updated {project_name}"}

@router.post("/update-all")
async def trigger_all_updates(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    await require_superuser(Authorize, db)
    projects = await run_in_thread(find_yml_files, get_settings().COMPOSE_DIR)
    for name in projects:
        await run_in_thread(update_compose_project, name)
    return {"message": "Updated all projects"}
