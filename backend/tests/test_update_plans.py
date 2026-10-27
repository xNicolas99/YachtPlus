"""Opt-in UTC update windows, durable task status and current administrator approval."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException, Request
from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.db.database import Base
from api.db.models.operations import Operation
from api.db.models.update_plans import UpdatePlan
from api.db.models.users import User
from api.routers import update_plans as routes
from api.services import update_plans as service
from api.services import watchtower


def moment(day=26, hour=23, *, offset=0):
    return datetime(2026, 10, day, hour, tzinfo=timezone(timedelta(hours=offset)))


def schedule(**values):
    return SimpleNamespace(enabled=True, excluded=False, weekdays=[0], window_start_hour=22,
                           window_end_hour=2, cadence_days=1, last_run=None, **values)


@pytest.mark.parametrize(("now", "expected"), [
    (moment(hour=21), False), (moment(hour=22), True), (moment(27, 1), True),
    (moment(27, 2), False), (moment(28, 1), False), (moment(27, 3, offset=2), True),
])
def test_overnight_window_belongs_to_starting_utc_weekday(now, expected):
    assert service.in_maintenance_window(schedule(), now) is expected


def test_next_due_respects_cadence_and_next_allowed_weekday():
    plan = schedule()
    plan.last_run = moment(26, 23).replace(tzinfo=None)
    assert service.next_due(plan, moment(27, 0)) == datetime(2026, 11, 2, 22, tzinfo=timezone.utc)
    plan.weekdays = list(range(7))
    plan.cadence_days = 2
    assert service.next_due(plan, moment(27, 0)) == moment(28, 23)


def test_all_day_window_and_disabled_or_excluded_plans():
    plan = schedule()
    plan.window_start_hour, plan.window_end_hour = 0, 24
    assert service.in_maintenance_window(plan, moment(26, 0))
    assert service.in_maintenance_window(plan, moment(26, 23))
    assert not service.in_maintenance_window(plan, moment(27, 0))
    plan.enabled = False
    assert service.next_due(plan, moment()) is None
    plan.enabled, plan.excluded = True, True
    assert service.next_due(plan, moment()) is None


@pytest.mark.parametrize("payload", [
    {"cadence_days": 0}, {"cadence_days": 1.5}, {"weekdays": []}, {"weekdays": [7]},
    {"weekdays": [True]}, {"window_start_hour": -1}, {"window_end_hour": 25},
    {"window_start_hour": 2, "window_end_hour": 2}, {"enabled": "true"}, {"unknown": True},
])
def test_invalid_or_ambiguous_schedule_is_rejected(payload):
    with pytest.raises(ValidationError):
        routes.PlanUpdate(**payload)


def test_plan_defaults_are_disabled_and_weekdays_are_normalized():
    assert routes.PlanUpdate().enabled is False
    assert routes.PlanUpdate(weekdays=[4, 0, 4]).weekdays == [0, 4]


class Auth:
    def __init__(self, username="admin", api_key=False):
        self.username, self.api_key = username, api_key

    async def jwt_required(self, **kwargs):
        return None

    async def get_jwt_subject(self, **kwargs):
        return self.username

    def is_api_key(self):
        return self.api_key


async def admin(db, **overrides):
    values = dict(username="admin", hashed_password="unused", is_active=True, is_superuser=True)
    values.update(overrides)
    actor = User(**values)
    db.add(actor)
    await db.commit()
    return actor


def patch_sessions(db, monkeypatch):
    monkeypatch.setattr(service, "SessionLocal", async_sessionmaker(bind=db.bind, expire_on_commit=False))
    monkeypatch.setattr(service, "existing_projects", AsyncMock(return_value={"demo"}))
    monkeypatch.setattr(service, "_utcnow", lambda: moment())


async def saved_plan(db, actor, **overrides):
    values = dict(project_name="demo", enabled=True, excluded=False, weekdays=[0], window_start_hour=22,
                  window_end_hour=2, cadence_days=1, owner_id=actor.id,
                  owner_username=actor.username, owner_auth_version=actor.auth_version)
    values.update(overrides)
    plan = UpdatePlan(**values)
    db.add(plan)
    await db.commit()
    return plan


@pytest.mark.asyncio
async def test_list_discovers_projects_without_creating_or_enabling_plans(db, monkeypatch):
    await admin(db)
    monkeypatch.setattr(service, "existing_projects", AsyncMock(return_value={"demo"}))
    result = await routes.list_update_plans(db=db, Authorize=Auth())
    assert result["items"][0]["configured"] is False
    assert result["items"][0]["enabled"] is False
    assert result["items"][0]["next_due"] is None
    assert list((await db.execute(select(UpdatePlan))).scalars()) == []


@pytest.mark.asyncio
async def test_save_exclusion_and_delete_restore_legacy_policy(db, monkeypatch):
    actor = await admin(db)
    monkeypatch.setattr(service, "existing_projects", AsyncMock(return_value={"demo"}))
    result = await routes.save_update_plan(MagicMock(spec=Request), "demo", routes.PlanUpdate(excluded=True), db, Auth())
    assert result["excluded"] is True and result["enabled"] is False
    plan = await db.get(UpdatePlan, "demo")
    assert plan.owner_id == actor.id and plan.owner_auth_version == actor.auth_version
    await routes.delete_update_plan(MagicMock(spec=Request), "demo", db, Auth())
    assert await db.get(UpdatePlan, "demo") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["save", "delete"])
async def test_api_keys_cannot_change_plans_even_for_administrators(db, monkeypatch, mutation):
    await admin(db)
    monkeypatch.setattr(service, "existing_projects", AsyncMock(return_value={"demo"}))
    with pytest.raises(HTTPException) as raised:
        if mutation == "save":
            await routes.save_update_plan(MagicMock(spec=Request), "demo", routes.PlanUpdate(), db, Auth(api_key=True))
        else:
            await routes.delete_update_plan(MagicMock(spec=Request), "demo", db, Auth(api_key=True))
    assert raised.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("flags", [{"is_superuser": False}, {"is_active": False}])
async def test_only_active_administrators_can_read_plans(db, flags):
    await admin(db, **flags)
    with pytest.raises(HTTPException) as raised:
        await routes.list_update_plans(db=db, Authorize=Auth())
    assert raised.value.status_code in (401, 403)


@pytest.mark.asyncio
async def test_unknown_project_cannot_gain_a_schedule(db, monkeypatch):
    await admin(db)
    monkeypatch.setattr(service, "existing_projects", AsyncMock(return_value=set()))
    with pytest.raises(HTTPException) as raised:
        await routes.save_update_plan(MagicMock(spec=Request), "missing", routes.PlanUpdate(enabled=True), db, Auth())
    assert raised.value.status_code == 404
    assert await db.get(UpdatePlan, "missing") is None


@pytest.mark.asyncio
async def test_due_plan_enqueues_once_and_reports_persistent_operation_result(db, monkeypatch):
    actor = await admin(db)
    await saved_plan(db, actor)
    patch_sessions(db, monkeypatch)
    runners = []

    async def submit(session, **kwargs):
        runners.append(kwargs["runner"])
        operation = Operation(kind=kwargs["kind"], resource=kwargs["resource"], action=kwargs["action"],
                              actor=actor.username, actor_id=actor.id, auth_version=actor.auth_version,
                              actor_instance=actor.account_instance,
                              worker_id="test-worker", heartbeat_at=moment(), status="queued")
        session.add(operation)
        await session.flush()
        kwargs["before_commit"](operation)
        assert (await session.get(UpdatePlan, "demo")).last_operation_id == operation.id
        await session.commit()
        return operation

    mocked = AsyncMock(side_effect=submit)
    monkeypatch.setattr(service.operations, "submit_operation", mocked)
    identifiers = await service.run_due_update_plans(now=moment())
    assert len(identifiers) == 1
    assert mocked.call_args.kwargs["kind"] == "compose.scheduled-update"
    assert await service.run_due_update_plans(now=moment()) == []
    mocked.assert_awaited_once()
    operation = await db.get(Operation, identifiers[0])
    operation.status, operation.error = "failed", "Operation failed. Check server logs for details."
    await db.commit()
    result = await routes.list_update_plans(db=db, Authorize=Auth())
    assert result["items"][0]["last_status"] == "failed"
    assert result["items"][0]["last_error"] == operation.error
    assert result["items"][0]["last_operation_id"] == identifiers[0]
    assert len(runners) == 1
    assert await service.run_due_update_plans(now=moment()) == []
    mocked.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", [{"excluded": True}, {"enabled": False}, {"weekdays": [1]}, {"last_run": moment()}])
async def test_excluded_disabled_not_due_or_outside_window_never_enqueues(db, monkeypatch, overrides):
    actor = await admin(db)
    await saved_plan(db, actor, **overrides)
    patch_sessions(db, monkeypatch)
    submit = AsyncMock()
    monkeypatch.setattr(service.operations, "submit_operation", submit)
    assert await service.run_due_update_plans(now=moment()) == []
    submit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["credentials", "inactive", "demoted", "deleted"])
async def test_stale_approving_account_disables_plan_before_queueing(db, monkeypatch, change):
    actor = await admin(db)
    await saved_plan(db, actor)
    if change == "credentials":
        actor.auth_version = "new-account-version"
    elif change == "inactive":
        actor.is_active = False
    elif change == "demoted":
        actor.is_superuser = False
    else:
        await db.delete(actor)
    await db.commit()
    patch_sessions(db, monkeypatch)
    submit = AsyncMock()
    monkeypatch.setattr(service.operations, "submit_operation", submit)
    assert await service.run_due_update_plans(now=moment()) == []
    submit.assert_not_awaited()
    await db.refresh(await db.get(UpdatePlan, "demo"))
    plan = await db.get(UpdatePlan, "demo")
    assert plan.enabled is False and plan.last_status == "blocked"
    assert "approval" in plan.last_error.lower()


@pytest.mark.asyncio
async def test_queue_failure_is_generic_and_does_not_consume_cadence(db, monkeypatch):
    actor = await admin(db)
    await saved_plan(db, actor)
    patch_sessions(db, monkeypatch)
    monkeypatch.setattr(service.operations, "submit_operation", AsyncMock(side_effect=RuntimeError("secret database internals")))
    assert await service.run_due_update_plans(now=moment()) == []
    plan = await db.get(UpdatePlan, "demo")
    await db.refresh(plan)
    assert plan.last_run is None
    assert plan.last_status == "failed"
    assert "secret" not in plan.last_error


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["excluded", "revision", "window", "credentials"])
async def test_queued_run_rechecks_plan_and_account_before_touching_docker(db, monkeypatch, change):
    actor = await admin(db)
    plan = await saved_plan(db, actor)
    runner = service._scheduled_runner(plan.project_name, plan.revision)
    if change == "excluded":
        plan.excluded = True
    elif change == "revision":
        plan.revision = "new-plan-revision"
    elif change == "window":
        plan.window_start_hour, plan.window_end_hour = 1, 2
    else:
        actor.auth_version = "new-version"
    await db.commit()
    patch_sessions(db, monkeypatch)
    action = MagicMock()
    monkeypatch.setattr("api.actions.compose._compose_action_sync", action)
    with pytest.raises(HTTPException):
        await runner(AsyncMock())
    action.assert_not_called()


@pytest.mark.asyncio
async def test_long_pull_cannot_recreate_services_after_window_closes(db, monkeypatch):
    actor = await admin(db)
    plan = await saved_plan(db, actor)
    patch_sessions(db, monkeypatch)
    clock = [moment()]
    monkeypatch.setattr(service, "_utcnow", lambda: clock[0])

    def action(name, command):
        clock[0] = moment(27, 2)

    mocked = MagicMock(side_effect=action)
    monkeypatch.setattr("api.actions.compose._compose_action_sync", mocked)
    with pytest.raises(HTTPException):
        await service._scheduled_runner(plan.project_name, plan.revision)(AsyncMock())
    mocked.assert_called_once_with("demo", "pull")


@pytest.mark.asyncio
async def test_scheduled_runner_pulls_then_recreates_within_approved_window(db, monkeypatch):
    actor = await admin(db)
    plan = await saved_plan(db, actor)
    patch_sessions(db, monkeypatch)
    action = MagicMock()
    monkeypatch.setattr("api.actions.compose._compose_action_sync", action)
    await service._scheduled_runner(plan.project_name, plan.revision)(AsyncMock())
    assert [call.args for call in action.call_args_list] == [("demo", "pull"), ("demo", "up")]


@pytest.mark.asyncio
async def test_window_is_rechecked_after_waiting_for_the_compose_executor(db, monkeypatch):
    import asyncio
    actor = await admin(db)
    plan = await saved_plan(db, actor)
    patch_sessions(db, monkeypatch)
    clock = [moment()]
    monkeypatch.setattr(service, "_utcnow", lambda: clock[0])

    async def delayed_executor(function):
        clock[0] = moment(27, 2)
        return await asyncio.to_thread(function)

    monkeypatch.setattr("api.actions.compose.run_in_thread", delayed_executor)
    action = MagicMock()
    monkeypatch.setattr("api.actions.compose._compose_action_sync", action)
    with pytest.raises(HTTPException):
        await service._scheduled_runner(plan.project_name, plan.revision)(AsyncMock())
    action.assert_not_called()


def test_legacy_daily_path_respects_all_saved_project_policies(tmp_path, monkeypatch):
    path = tmp_path / "policy.db"
    engine = create_engine("sqlite:///" + str(path))
    UpdatePlan.__table__.create(engine)
    from sqlalchemy.orm import Session
    with Session(engine) as db:
        db.add_all([UpdatePlan(project_name="excluded", excluded=True),
                    UpdatePlan(project_name="scheduled", enabled=True),
                    UpdatePlan(project_name="disabled", enabled=False)])
        db.commit()
    engine.dispose()
    monkeypatch.setattr(watchtower, "get_settings", lambda: SimpleNamespace(
        COMPOSE_AUTO_UPDATE=True, COMPOSE_DIR=str(tmp_path), DATABASE_URL="sqlite:///" + str(path)))
    monkeypatch.setattr(watchtower, "find_yml_files", lambda _: {name: "file" for name in ["excluded", "scheduled", "disabled", "legacy"]})
    action = MagicMock()
    monkeypatch.setattr(watchtower, "_compose_action_sync", action)
    watchtower.update_all_projects()
    assert [call.args for call in action.call_args_list] == [("legacy", "pull"), ("legacy", "up")]


def test_legacy_rechecks_exclusions_between_projects_and_before_recreation(tmp_path, monkeypatch):
    path = tmp_path / "policy.db"
    engine = create_engine("sqlite:///" + str(path))
    UpdatePlan.__table__.create(engine)
    from sqlalchemy.orm import Session
    monkeypatch.setattr(watchtower, "get_settings", lambda: SimpleNamespace(
        COMPOSE_AUTO_UPDATE=True, COMPOSE_DIR=str(tmp_path), DATABASE_URL="sqlite:///" + str(path)))
    monkeypatch.setattr(watchtower, "find_yml_files", lambda _: {"pulling": "file", "later": "file"})

    def exclude_while_pulling(project, command):
        with Session(engine) as db:
            db.add_all([UpdatePlan(project_name="pulling", excluded=True), UpdatePlan(project_name="later", excluded=True)])
            db.commit()

    action = MagicMock(side_effect=exclude_while_pulling)
    monkeypatch.setattr(watchtower, "_compose_action_sync", action)
    try:
        watchtower.update_all_projects()
        action.assert_called_once_with("pulling", "pull")
    finally:
        engine.dispose()
