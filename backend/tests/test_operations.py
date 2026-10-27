"""Tasks retain status across requests without retaining sensitive payloads."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.db.database import Base
from api.db.models.operations import Operation
from api.db.models.users import User
from api.routers import operations as router
from api.services import operations


class Auth:
    def __init__(self, username, api_key=False):
        self.username = username
        self.api_key = api_key

    async def jwt_required(self, **kwargs):
        pass

    async def get_jwt_subject(self):
        return self.username

    def is_api_key(self):
        return self.api_key


@pytest_asyncio.fixture
async def setup(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(operations, "SessionLocal", factory)
    monkeypatch.setattr(operations.get_settings(), "DISABLE_AUTH", False)
    await operations.stop_operation_service()
    async with factory() as db:
        alice = User(username="alice", hashed_password="hash", is_active=True, perm_start=True,
                     perm_restart=True, auth_version="a" * 64)
        bob = User(username="bob", hashed_password="hash", is_active=True, perm_start=True,
                   auth_version="b" * 64)
        admin = User(username="admin", hashed_password="hash", is_active=True, is_superuser=True,
                     auth_version="c" * 64)
        db.add_all([alice, bob, admin])
        await db.commit()
        yield SimpleNamespace(db=db, factory=factory, alice=alice, bob=bob, admin=admin)
    await operations.stop_operation_service()
    await engine.dispose()


async def _status(factory, operation_id):
    async with factory() as db:
        return await db.get(Operation, operation_id)


@pytest.mark.asyncio
async def test_submitted_work_outlives_caller_and_exposes_only_status(setup):
    ready = asyncio.Event()
    finish = asyncio.Event()

    async def run(report):
        await report("Copying data")
        ready.set()
        await finish.wait()
        return {"password": "must-not-persist", "path": "/secret/server/path"}

    task = await operations.submit_operation(setup.db, kind="volume.backup", resource="data",
                                             actor=setup.alice, runner=run)
    assert task.status == "queued"
    await ready.wait()
    current = await _status(setup.factory, task.id)
    assert current.status == "running" and current.phase == "Copying data"
    public = operations.public_operation(current)
    assert public["created_at"].tzinfo is timezone.utc
    assert not {"auth_version", "actor_id", "actor_instance", "worker_id", "heartbeat_at", "result"} & public.keys()
    assert not public["retryable"]
    finish.set()
    await operations.wait_for_operation(task.id)
    current = await _status(setup.factory, task.id)
    assert current.status == "succeeded" and current.finished_at
    assert "must-not-persist" not in str(operations.public_operation(current))


@pytest.mark.asyncio
async def test_failed_runner_stores_generic_error_not_exception_or_credentials(setup):
    async def run(report):
        raise ValueError("PASSWORD=must-not-persist /secret/path")

    task = await operations.submit_operation(setup.db, kind="volume.backup", resource="data",
                                             actor=setup.alice, runner=run)
    with pytest.raises(HTTPException) as error:
        await operations.wait_for_operation(task.id)
    assert error.value.status_code == 500
    current = await _status(setup.factory, task.id)
    assert current.status == "failed"
    assert "PASSWORD" not in current.error and "/secret" not in current.error


@pytest.mark.asyncio
async def test_shutdown_records_interruption_without_replaying_work(setup):
    started = asyncio.Event()

    async def run(report):
        started.set()
        await asyncio.Event().wait()

    task = await operations.submit_operation(setup.db, kind="volume.backup", resource="data",
                                             actor=setup.alice, runner=run)
    await started.wait()
    await operations.stop_operation_service()
    assert (await _status(setup.factory, task.id)).status == "interrupted"


@pytest.mark.asyncio
async def test_restart_expires_dead_worker_but_keeps_other_live_workers(setup):
    now = datetime.now(timezone.utc)
    for status, age, worker in [("running", 60, "dead"), ("queued", 0, "alive"), ("succeeded", 60, "done")]:
        setup.db.add(Operation(id=worker, kind="container.action", action="start", resource="web",
                               actor="alice", actor_id=setup.alice.id, actor_instance=setup.alice.account_instance, auth_version=setup.alice.auth_version,
                               status=status, worker_id=worker, heartbeat_at=now - timedelta(seconds=age)))
    await setup.db.commit()
    await operations.start_operation_service()
    assert operations.get_operation_loop() is asyncio.get_running_loop()
    assert (await _status(setup.factory, "dead")).status == "interrupted"
    assert (await _status(setup.factory, "alive")).status == "queued"
    assert (await _status(setup.factory, "done")).status == "succeeded"


@pytest.mark.asyncio
async def test_permissions_are_checked_again_when_queued_work_starts(setup, monkeypatch):
    monkeypatch.setattr(operations, "MAX_CONCURRENT", 1)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def busy(report):
        entered.set()
        await release.wait()

    first = await operations.submit_operation(setup.db, kind="volume.backup", resource="data",
                                              actor=setup.alice, runner=busy)
    await entered.wait()
    from api.actions import apps
    action = AsyncMock()
    monkeypatch.setattr(apps, "app_action", action)
    queued = await operations.submit_operation(setup.db, kind="container.action", resource="web",
                                               action="start", actor=setup.alice)
    setup.alice.perm_start = False
    await setup.db.commit()
    release.set()
    with pytest.raises(HTTPException) as error:
        await operations.wait_for_operation(queued.id)
    assert error.value.status_code == 403
    action.assert_not_awaited()
    await operations.wait_for_operation(first.id)


@pytest.mark.asyncio
async def test_credential_rotation_invalidates_queued_work(setup, monkeypatch):
    gate = asyncio.Event()
    entered = asyncio.Event()
    monkeypatch.setattr(operations, "MAX_CONCURRENT", 1)

    async def busy(report):
        entered.set()
        await gate.wait()

    await operations.submit_operation(setup.db, kind="volume.backup", resource="data", actor=setup.alice, runner=busy)
    await entered.wait()
    from api.actions import apps
    action = AsyncMock()
    monkeypatch.setattr(apps, "app_action", action)
    queued = await operations.submit_operation(setup.db, kind="container.action", resource="web", action="start", actor=setup.alice)
    setup.alice.auth_version = "rotated"
    await setup.db.commit()
    gate.set()
    with pytest.raises(HTTPException) as error:
        await operations.wait_for_operation(queued.id)
    assert error.value.status_code == 401
    action.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_limit_rejects_before_creating_record(setup, monkeypatch):
    monkeypatch.setattr(operations, "MAX_PENDING", 0)
    with pytest.raises(HTTPException) as error:
        await operations.submit_operation(setup.db, kind="container.action", resource="web", action="start", actor=setup.alice)
    assert error.value.status_code == 429
    assert not (await setup.db.execute(select(Operation))).scalars().all()


@pytest.mark.asyncio
async def test_container_update_requires_both_create_and_restart_permissions(setup):
    setup.alice.perm_start = False
    await setup.db.commit()
    with pytest.raises(HTTPException) as error:
        await operations.submit_operation(setup.db, kind="container.action", resource="web", action="update", actor=setup.alice)
    assert error.value.status_code == 403
    assert not (await setup.db.execute(select(Operation))).scalars().all()


@pytest.mark.asyncio
async def test_deployment_payload_is_not_persisted_and_conflicts_do_not_queue(setup, monkeypatch):
    from api.actions import apps
    from api.db.schemas.apps import DeployForm
    monkeypatch.setattr(apps, "check_container_conflicts", AsyncMock(return_value=[]))
    deploy = AsyncMock(return_value={"logs": "private container logs"})
    monkeypatch.setattr(apps, "deploy_app", deploy)
    payload = DeployForm(name="web", image="example/web", env=[{"name": "PASSWORD", "default": "private-password"}])
    response = await router.create_deployment(None, payload, setup.db, Auth("alice"))
    assert response["kind"] == "container.deploy" and not response["retryable"]
    await operations.wait_for_operation(response["id"])
    deploy.assert_awaited_once()
    persisted = await _status(setup.factory, response["id"])
    assert "private-password" not in str(vars(persisted))
    assert "private container logs" not in str(vars(persisted))

    monkeypatch.setattr(apps, "check_container_conflicts", AsyncMock(return_value=[{"type": "port"}]))
    conflict = await router.create_deployment(None, payload, setup.db, Auth("alice"))
    assert conflict.status_code == 409
    records = (await setup.db.execute(select(Operation))).scalars().all()
    assert len(records) == 1


@pytest.mark.asyncio
async def test_owner_scope_pagination_and_admin_visibility(setup):
    now = datetime.now(timezone.utc)
    for number, actor in enumerate([setup.alice, setup.alice, setup.bob]):
        setup.db.add(Operation(id=str(number), kind="container.action", resource="web", action="start",
                               actor=actor.username, actor_id=actor.id, actor_instance=actor.account_instance, status="succeeded",
                               worker_id="old", heartbeat_at=now))
    await setup.db.commit()
    mine = await router.list_operations(state=None, limit=1, offset=1, db=setup.db, Authorize=Auth("alice"))
    assert mine["total"] == 2 and len(mine["items"]) == 1
    all_tasks = await router.list_operations(state=None, limit=25, offset=0, db=setup.db, Authorize=Auth("admin"))
    assert all_tasks["total"] == 3
    with pytest.raises(HTTPException) as missing:
        await router.get_operation("2", setup.db, Auth("alice"))
    assert missing.value.status_code == 404


@pytest.mark.asyncio
async def test_api_key_cannot_submit_or_retry_work(setup):
    payload = router.OperationRequest(kind="container.action", resource="web", action="start")
    with pytest.raises(HTTPException) as error:
        await router.create_operation(None, payload, setup.db, Auth("alice", api_key=True))
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        await router.retry_operation(None, "missing", setup.db, Auth("alice", api_key=True))
    assert error.value.status_code == 403


@pytest.mark.parametrize("kind,resource,action", [
    ("anything", "web", "start"), ("container.action", "../secret", "start"),
    ("container.action", "web", "exec"), ("image.pull", "registry/image;cmd", None),
    ("image.pull", "https://registry/image", None), ("compose.action", "../stack", "up"),
])
def test_operation_descriptors_are_strictly_allowlisted(kind, resource, action):
    with pytest.raises(HTTPException):
        operations.validate_descriptor(kind, resource, action)


@pytest.mark.asyncio
async def test_retry_checks_current_permission_and_refuses_unknown_runner(setup):
    now = datetime.now(timezone.utc)
    for kind in ("container.action", "volume.backup"):
        setup.db.add(Operation(id=kind, kind=kind, resource="web", action="remove",
                               actor="alice", actor_id=setup.alice.id, actor_instance=setup.alice.account_instance, status="failed",
                               retry_supported=True,
                               worker_id="old", heartbeat_at=now))
    await setup.db.commit()
    with pytest.raises(HTTPException) as permission:
        await router.retry_operation(None, "container.action", setup.db, Auth("alice"))
    assert permission.value.status_code == 403
    with pytest.raises(HTTPException) as unsupported:
        await router.retry_operation(None, "volume.backup", setup.db, Auth("alice"))
    assert unsupported.value.status_code == 409


@pytest.mark.asyncio
async def test_code_owned_runner_cannot_be_replayed_as_a_generic_builtin(setup):
    async def guarded_runner(report):
        raise HTTPException(409, "Scheduled policy changed")

    operation = await operations.submit_operation(setup.db, kind="compose.action", resource="web", action="update",
                                                  actor=setup.admin, runner=guarded_runner)
    with pytest.raises(HTTPException):
        await operations.wait_for_operation(operation.id)
    await setup.db.refresh(operation)
    assert operation.status == "failed"
    assert operations.public_operation(operation)["retryable"] is False
    with pytest.raises(HTTPException) as error:
        await router.retry_operation(None, operation.id, setup.db, Auth("admin"))
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_new_account_cannot_inherit_deleted_accounts_task_history(setup):
    from sqlalchemy import delete
    old_id = setup.admin.id
    old_instance = setup.admin.account_instance
    setup.db.add(Operation(id="previous-account", kind="container.action", resource="web", action="start",
                           actor="admin", actor_id=old_id, actor_instance=old_instance, status="succeeded",
                           worker_id="old", heartbeat_at=datetime.now(timezone.utc)))
    await setup.db.execute(delete(User).where(User.id == old_id))
    await setup.db.commit()
    setup.db.expunge(setup.admin)
    replacement = User(username="admin", hashed_password="hash", is_active=True, perm_start=True)
    setup.db.add(replacement)
    await setup.db.commit()
    assert replacement.id == old_id
    assert replacement.account_instance != old_instance
    result = await router.list_operations(state=None, limit=25, offset=0, db=setup.db, Authorize=Auth("admin"))
    assert result == {"items": [], "total": 0}
    with pytest.raises(HTTPException) as error:
        await router.get_operation("previous-account", setup.db, Auth("admin"))
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_existing_account_keeps_history_after_password_version_rotation(setup):
    setup.db.add(Operation(id="history", kind="container.action", resource="web", action="start",
                           actor="alice", actor_id=setup.alice.id, actor_instance=setup.alice.account_instance,
                           auth_version=setup.alice.auth_version, status="succeeded", worker_id="old",
                           heartbeat_at=datetime.now(timezone.utc)))
    setup.alice.auth_version = "new-password-version"
    await setup.db.commit()
    response = await router.get_operation("history", setup.db, Auth("alice"))
    assert response["id"] == "history"


@pytest.mark.asyncio
async def test_image_update_uses_inspected_image_update_action(setup, monkeypatch):
    from api.actions import resources
    update_image = AsyncMock()
    write_image = AsyncMock()
    monkeypatch.setattr(resources, "update_image", update_image)
    monkeypatch.setattr(resources, "write_image", write_image)
    task = await operations.submit_operation(setup.db, kind="image.pull", resource="sha256:123abc",
                                             action="update", actor=setup.admin)
    await operations.wait_for_operation(task.id)
    update_image.assert_awaited_once_with("sha256:123abc")
    write_image.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelling_status_wait_does_not_cancel_server_work(setup):
    ready = asyncio.Event()
    finish = asyncio.Event()

    async def run(report):
        ready.set()
        await finish.wait()

    task = await operations.submit_operation(setup.db, kind="volume.backup", resource="data", actor=setup.alice, runner=run)
    await ready.wait()
    waiter = asyncio.create_task(operations.wait_for_operation(task.id))
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert not operations._tasks[task.id].done()
    finish.set()
    await operations.wait_for_operation(task.id)
    assert (await _status(setup.factory, task.id)).status == "succeeded"


@pytest.mark.asyncio
async def test_self_restart_handoff_never_claims_verified_completion(setup, monkeypatch):
    from api.actions import apps
    restart = AsyncMock()

    async def action(name, verb, background_tasks):
        background_tasks.add_task(restart)

    monkeypatch.setattr(apps, "app_action", action)
    task = await operations.submit_operation(setup.db, kind="container.action", resource="yachtplus", action="restart", actor=setup.admin)
    with pytest.raises(HTTPException):
        await operations.wait_for_operation(task.id)
    restart.assert_awaited_once()
    assert (await _status(setup.factory, task.id)).status == "interrupted"


@pytest.mark.asyncio
async def test_atomic_link_hook_rolls_back_a_failed_submission(setup):
    def invalid_link(operation):
        assert operation.id
        raise ValueError("Could not associate scheduled work")

    with pytest.raises(ValueError):
        await operations.submit_operation(setup.db, kind="container.action", resource="web", action="start",
                                           actor=setup.alice, before_commit=invalid_link)
    assert not (await setup.db.execute(select(Operation))).scalars().all()
