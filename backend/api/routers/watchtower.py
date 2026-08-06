from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from api.auth.jwt import get_auth_wrapper
from api.auth.auth import auth_check, require_superuser
from api.services.watchtower import update_compose_project, update_all_projects
from api.utils.auth import get_db

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
    background_tasks.add_task(update_compose_project, project_name)
    return {"message": f"Update triggered for {project_name}"}

@router.post("/update-all")
async def trigger_all_updates(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    await require_superuser(Authorize, db)
    background_tasks.add_task(update_all_projects)
    return {"message": "Update triggered for all projects"}
