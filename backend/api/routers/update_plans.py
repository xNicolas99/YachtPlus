"""Administrator-only, explicitly saved Compose update schedules."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.auth import require_superuser
from api.auth.jwt import get_auth_wrapper
from api.db.models.update_plans import UpdatePlan
from api.services import update_plans
from api.settings import get_settings
from api.utils.audit import log_activity
from api.utils.auth import get_db
from api.utils.compose import validate_compose_project_name
from api.utils.security import limiter

router = APIRouter()


class PlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool = False
    excluded: StrictBool = False
    weekdays: list[StrictInt] = Field(default_factory=lambda: list(range(7)), min_length=1, max_length=7)
    window_start_hour: int = Field(default=0, strict=True, ge=0, le=23)
    window_end_hour: int = Field(default=24, strict=True, ge=0, le=24)
    cadence_days: int = Field(default=1, strict=True, ge=1, le=3650)

    @model_validator(mode="after")
    def valid_window(self):
        if any(day < 0 or day > 6 for day in self.weekdays):
            raise ValueError("Weekdays must be between Monday (0) and Sunday (6)")
        if self.window_start_hour == self.window_end_hour:
            raise ValueError("Use 00:00–24:00 for an all-day window")
        self.weekdays = sorted(set(self.weekdays))
        return self


def _public_plan(name, plan, exists, now=None):
    defaults = PlanUpdate().model_dump()
    values = {key: getattr(plan, key) for key in defaults} if plan else defaults
    return {
        "project_name": name, "configured": plan is not None, "project_exists": exists,
        **values,
        "last_run": plan.last_run if plan else None,
        "last_status": plan.last_status if plan else "never",
        "last_error": plan.last_error if plan else None,
        "last_operation_id": plan.last_operation_id if plan else None,
        "next_due": update_plans.next_due(plan, now) if plan and exists else None,
    }


async def _admin(db, Authorize, *, mutation=False):
    actor = await require_superuser(Authorize, db)
    if mutation and Authorize.is_api_key():
        raise HTTPException(403, "API keys cannot change update plans")
    return actor


@router.get("")
@router.get("/", include_in_schema=False)
async def list_update_plans(db: AsyncSession = Depends(get_db), Authorize=Depends(get_auth_wrapper)):
    await _admin(db, Authorize)
    projects = await update_plans.existing_projects()
    plans = list((await db.execute(select(UpdatePlan))).scalars())
    await update_plans.refresh_plan_statuses(db, plans)
    by_name = {plan.project_name: plan for plan in plans}
    return {
        "items": [_public_plan(name, by_name.get(name), name in projects)
                  for name in sorted(projects | by_name.keys())],
        "legacy_auto_update": bool(get_settings().COMPOSE_AUTO_UPDATE),
        "timezone": "UTC",
    }


@router.put("/{project_name}")
@limiter.limit("20/minute")
async def save_update_plan(
    request: Request, project_name: str, payload: PlanUpdate,
    db: AsyncSession = Depends(get_db), Authorize=Depends(get_auth_wrapper),
    response: Response = None,
):
    actor = await _admin(db, Authorize, mutation=True)
    validate_compose_project_name(project_name)
    if len(project_name) > 128 or "\n" in project_name or project_name not in await update_plans.existing_projects():
        raise HTTPException(404, "Compose project not found")
    if payload.enabled and (not actor.id or not actor.auth_version):
        raise HTTPException(403, "Sign in with a persisted administrator account to authorize scheduled updates")
    plan = await db.get(UpdatePlan, project_name)
    if plan is None:
        plan = UpdatePlan(project_name=project_name)
        db.add(plan)
    for key, value in payload.model_dump().items():
        setattr(plan, key, value)
    plan.owner_id = actor.id
    plan.owner_username = actor.username
    plan.owner_auth_version = actor.auth_version
    plan.revision = secrets.token_hex(16)
    plan.updated_at = update_plans._utcnow()
    if plan.last_status == "blocked":
        plan.last_status = "never"
        plan.last_error = None
    await db.commit()
    await db.refresh(plan)
    await log_activity(db, actor.username, "update_plan.saved", project_name)
    return _public_plan(project_name, plan, True)


@router.delete("/{project_name}")
@limiter.limit("20/minute")
async def delete_update_plan(
    request: Request, project_name: str,
    db: AsyncSession = Depends(get_db), Authorize=Depends(get_auth_wrapper),
    response: Response = None,
):
    actor = await _admin(db, Authorize, mutation=True)
    validate_compose_project_name(project_name)
    plan = await db.get(UpdatePlan, project_name)
    if plan is None:
        raise HTTPException(404, "Update plan not found")
    await db.delete(plan)
    await db.commit()
    await log_activity(db, actor.username, "update_plan.removed", project_name)
    return {"deleted": True, "legacy_auto_update": bool(get_settings().COMPOSE_AUTO_UPDATE)}
