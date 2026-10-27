"""Run opt-in project updates inside UTC maintenance windows, once per cadence."""

import asyncio
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime, time, timedelta, timezone
import logging

from fastapi import HTTPException
from sqlalchemy import or_, select, update

from api.db.database import SessionLocal
from api.db.models.operations import Operation
from api.db.models.update_plans import UpdatePlan
from api.db.models.users import User
from api.services import operations
from api.settings import get_settings
from api.utils.compose import find_yml_files, validate_compose_project_name

logger = logging.getLogger(__name__)
ACTIVE_STATUSES = {"queued", "running"}


def _utcnow():
    return datetime.now(timezone.utc)


def as_utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _window(plan, day):
    beginning = datetime.combine(day, time.min, tzinfo=timezone.utc) + timedelta(hours=plan.window_start_hour)
    end = datetime.combine(day, time.min, tzinfo=timezone.utc) + timedelta(hours=plan.window_end_hour)
    if end <= beginning:
        end += timedelta(days=1)
    return beginning, end


def in_maintenance_window(plan, now):
    now = as_utc(now)
    # Overnight windows belong to the selected day on which they BEGIN.
    for day in (now.date() - timedelta(days=1), now.date()):
        beginning, end = _window(plan, day)
        if day.weekday() in plan.weekdays and beginning <= now < end:
            return True
    return False


def next_due(plan, now=None):
    if not plan.enabled or plan.excluded:
        return None
    now = as_utc(now or _utcnow())
    due = as_utc(plan.last_run) + timedelta(days=plan.cadence_days) if plan.last_run else now
    earliest = max(now, due)
    for offset in range(9):
        day = earliest.date() + timedelta(days=offset - 1)
        if day.weekday() not in plan.weekdays:
            continue
        beginning, end = _window(plan, day)
        candidate = max(beginning, earliest)
        if candidate < end:
            return candidate
    return None


async def existing_projects():
    files = await asyncio.to_thread(find_yml_files, get_settings().COMPOSE_DIR)
    valid = set()
    for name in files:
        try:
            if not isinstance(name, str) or len(name) > 128 or "\n" in name:
                continue
            validate_compose_project_name(name)
        except HTTPException:
            continue
        valid.add(name)
    return valid


async def refresh_plan_statuses(db, plans):
    identifiers = [plan.last_operation_id for plan in plans if plan.last_operation_id]
    if not identifiers:
        return
    records = {operation.id: operation for operation in (await db.execute(
        select(Operation).where(Operation.id.in_(identifiers))
    )).scalars()}
    changed = False
    for plan in plans:
        operation = records.get(plan.last_operation_id)
        if (operation and plan.last_status in ACTIVE_STATUSES
                and (plan.last_status != operation.status or plan.last_error != operation.error)):
            plan.last_status = operation.status
            plan.last_error = operation.error[:255] if operation.error else None
            changed = True
    if changed:
        await db.commit()


async def _plan_actor(db, plan):
    actor = await db.get(User, plan.owner_id) if plan.owner_id else None
    if (not actor or not actor.is_active or not actor.is_superuser
            or not plan.owner_auth_version or actor.auth_version != plan.owner_auth_version
            or actor.username != plan.owner_username):
        raise HTTPException(403, "The plan requires renewed administrator approval")
    return actor


async def _check_scheduled_run(project_name, revision):
    async with SessionLocal() as db:
        plan = await db.get(UpdatePlan, project_name)
        if not plan or plan.revision != revision or not plan.enabled or plan.excluded:
            raise HTTPException(409, "The update plan changed before execution")
        await _plan_actor(db, plan)
        if not in_maintenance_window(plan, _utcnow()):
            raise HTTPException(409, "The maintenance window has closed")
    if project_name not in await existing_projects():
        raise HTTPException(404, "Compose project not found")


def _scheduled_runner(project_name, revision):
    async def run(report):
        await _check_scheduled_run(project_name, revision)
        await report("Pulling scheduled stack images")
        await _scheduled_action(project_name, revision, "pull")
        # A long pull or a queue delay must not restart services after the
        # approved window closes or after an administrator changes the plan.
        await _check_scheduled_run(project_name, revision)
        await report("Recreating scheduled stack services")
        await _scheduled_action(project_name, revision, "up")
    return run


async def _scheduled_action(project_name, revision, action):
    from api.actions.compose import _compose_action_sync, run_in_thread
    loop = asyncio.get_running_loop()

    def execute():
        # The Compose executor itself can queue work behind long-running
        # pulls. Recheck on the API loop AFTER that wait, before subprocess.
        approval = asyncio.run_coroutine_threadsafe(_check_scheduled_run(project_name, revision), loop)
        try:
            approval.result(timeout=30)
        except FutureTimeout:
            approval.cancel()
            raise HTTPException(503, "Scheduled update approval check timed out") from None
        return _compose_action_sync(project_name, action)

    return await run_in_thread(execute)


async def run_due_update_plans(*, now=None):
    """Called on the API event loop by the elected scheduler; safe to repeat."""
    now = as_utc(now or _utcnow())
    projects = await existing_projects()
    submitted = []
    async with SessionLocal() as db:
        plans = list((await db.execute(select(UpdatePlan))).scalars())
        await refresh_plan_statuses(db, plans)
        names = [plan.project_name for plan in plans]
    for name in names:
        # A failed enqueue rolls back only this project's claim. Keeping a
        # separate session also avoids expired ORM rows after a rollback.
        async with SessionLocal() as db:
            plan = await db.get(UpdatePlan, name)
            if plan is None:
                continue
            if not plan.enabled or plan.excluded or plan.last_status in ACTIVE_STATUSES:
                continue
            if plan.project_name not in projects:
                plan.last_status = "blocked"
                plan.last_error = "The project is unavailable. Restore it or remove this plan."
                await db.commit()
                continue
            due = next_due(plan, now)
            if due is None or due > now or not in_maintenance_window(plan, now):
                continue
            try:
                actor = await _plan_actor(db, plan)
            except HTTPException:
                plan.enabled = False
                plan.last_status = "blocked"
                plan.last_error = "Administrator approval expired. Save the plan again to authorize future updates."
                await db.commit()
                continue
            threshold = now - timedelta(days=plan.cadence_days)
            result = await db.execute(update(UpdatePlan).where(
                UpdatePlan.project_name == plan.project_name,
                UpdatePlan.revision == plan.revision,
                UpdatePlan.enabled.is_(True), UpdatePlan.excluded.is_(False),
                or_(UpdatePlan.last_run.is_(None), UpdatePlan.last_run <= threshold),
            ).values(last_run=now, last_status="queued", last_error=None))
            if result.rowcount != 1:
                await db.rollback()
                continue
            try:
                revision = plan.revision

                def attach_operation(operation):
                    plan.last_operation_id = operation.id

                operation = await operations.submit_operation(
                    db, kind="compose.scheduled-update", action="update", resource=plan.project_name,
                    actor=actor, runner=_scheduled_runner(plan.project_name, plan.revision),
                    before_commit=attach_operation,
                )
                submitted.append(operation.id)
            except Exception:
                await db.rollback()
                logger.exception("Could not enqueue a scheduled Compose update")
                # No raw subprocess/SQL/credential error reaches the UI.
                await db.execute(update(UpdatePlan).where(
                    UpdatePlan.project_name == name,
                    UpdatePlan.revision == revision,
                ).values(last_status="failed", last_error="The scheduled update could not be queued. It will be retried during an eligible window."))
                await db.commit()
    return submitted
