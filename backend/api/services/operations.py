"""Bounded background work with durable, non-sensitive status records.

The release image runs one API worker. Runner closures stay in memory and are
never replayed after a restart: unfinished records become interrupted instead.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import logging
import os
import re
import uuid

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select, update

from api.db.database import SessionLocal
from api.db.models.operations import Operation
from api.db.models.users import User
from api.settings import get_settings
from api.utils.audit import log_activity

logger = logging.getLogger(__name__)
MAX_PENDING = 32
MAX_CONCURRENT = 2
ACTIVE_STATUSES = {"queued", "running"}
TERMINAL_STATUSES = {"succeeded", "failed", "interrupted"}
BUILTIN_KINDS = {"container.action", "compose.action", "image.pull"}
CONTAINER_PERMISSIONS = {
    "start": "perm_start", "stop": "perm_stop", "restart": "perm_restart",
    "remove": "perm_delete", "kill": "perm_delete", "pause": "perm_stop",
    "unpause": "perm_start", "update": "perm_restart",
}
COMPOSE_PERMISSIONS = {
    "up": "perm_start", "create": "perm_start", "start": "perm_start",
    "stop": "perm_stop", "restart": "perm_restart", "down": "perm_delete",
    "kill": "perm_delete", "rm": "perm_delete", "delete": "perm_delete",
    "pull": "perm_restart", "update": "superuser",
}
_tasks = {}
_limiters = {}
_submit_locks = {}
_worker_id = str(uuid.uuid4())
_worker_pid = os.getpid()
_operation_loop = None
_heartbeat_task = None
LEASE_SECONDS = 30


@dataclass
class Outcome:
    result: object = None
    error: str | None = None
    status_code: int = 500


class UnverifiedRestart(Exception):
    """Restart handoff cannot prove completion from the process being restarted."""


def _utcnow():
    return datetime.now(timezone.utc)


def _loop_lock():
    loop = asyncio.get_running_loop()
    return _submit_locks.setdefault(loop, asyncio.Lock())


def public_operation(operation):
    """Explicit allowlist: account versions, payloads and daemon output stay private."""
    result = {
        key: getattr(operation, key)
        for key in ("id", "kind", "resource", "action", "actor", "status", "phase",
                    "error", "created_at", "started_at", "finished_at")
    } | {"retryable": bool(operation.retry_supported) and operation.kind in BUILTIN_KINDS and operation.status in {"failed", "interrupted"}}
    for key in ("created_at", "started_at", "finished_at"):
        if result[key] is not None and result[key].tzinfo is None:
            # SQLite strips timezone metadata from UTC DateTime values.
            result[key] = result[key].replace(tzinfo=timezone.utc)
    return result


def required_permission(kind, action=None):
    if kind == "container.action":
        permission = CONTAINER_PERMISSIONS.get(action)
    elif kind == "compose.action":
        permission = COMPOSE_PERMISSIONS.get(action)
    elif kind == "image.pull" and action in (None, "update"):
        permission = "superuser"
    elif kind == "container.deploy":
        permission = "perm_restart" if action == "edit" else "perm_start"
    else:
        permission = None
    if not permission:
        raise HTTPException(422, "Unsupported operation kind or action")
    return permission


def validate_descriptor(kind, resource, action=None):
    if kind not in BUILTIN_KINDS:
        raise HTTPException(422, "Unsupported operation kind")
    required_permission(kind, action)
    if kind == "image.pull":
        if (not isinstance(resource, str) or len(resource) > 512
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:@-]*", resource)
                or "://" in resource):
            raise HTTPException(422, "Invalid image reference")
    elif kind == "container.action":
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}", resource):
            raise HTTPException(422, "Invalid container identifier")
    else:
        from api.utils.compose import validate_compose_project_name
        validate_compose_project_name(resource)


def check_actor_permission(actor, permission):
    if not actor or not actor.is_active:
        raise HTTPException(401, "User account is unavailable")
    if actor.is_superuser:
        return
    if permission == "superuser" or not getattr(actor, permission, False):
        raise HTTPException(403, "Permission is required for this operation")


def check_operation_permission(actor, kind, action):
    check_actor_permission(actor, required_permission(kind, action))
    if (kind == "container.action" and action == "update") or (kind == "container.deploy" and action == "edit"):
        check_actor_permission(actor, "perm_start")


async def resolve_actor(db, Authorize):
    from api.auth.auth import auth_check
    await auth_check(Authorize)
    if get_settings().DISABLE_AUTH:
        return User(id=0, username="dev", is_active=True, is_superuser=True, account_instance="development")
    username = await Authorize.get_jwt_subject()
    actor = (await db.execute(select(User).where(User.username == username))).scalars().first()
    if not actor or not actor.is_active:
        raise HTTPException(401, "User account is unavailable")
    return actor


async def _fresh_actor(operation):
    if operation.actor_id == 0 and get_settings().DISABLE_AUTH:
        return User(id=0, username="dev", is_active=True, is_superuser=True, account_instance="development")
    async with SessionLocal() as db:
        actor = (await db.execute(select(User).where(User.id == operation.actor_id))).scalars().first()
        if (not actor or not actor.is_active or actor.username != operation.actor
                or actor.account_instance != operation.actor_instance
                or not operation.auth_version or actor.auth_version != operation.auth_version):
            raise HTTPException(401, "Account credentials changed before the operation started")
        return actor


async def _write_status(operation_id, **values):
    async with SessionLocal() as db:
        await db.execute(update(Operation).where(Operation.id == operation_id).values(**values))
        await db.commit()


async def _builtin_runner(operation, report):
    actor = await _fresh_actor(operation)
    check_operation_permission(actor, operation.kind, operation.action)
    if operation.kind == "container.action":
        from api.actions import apps
        await report("Updating container" if operation.action == "update" else "Applying container action")
        if operation.action == "update":
            await apps.app_update(operation.resource)
        else:
            handoff = BackgroundTasks()
            await apps.app_action(operation.resource, operation.action, handoff)
            if handoff.tasks:
                await report("Restart requested; reconnect to verify")
                await handoff()
                raise UnverifiedRestart()
    elif operation.kind == "compose.action":
        from api.actions import compose
        if operation.action == "update":
            await report("Pulling stack images")
            await compose.compose_action(operation.resource, "pull")
            actor = await _fresh_actor(operation)
            check_operation_permission(actor, operation.kind, operation.action)
            await report("Recreating stack services")
            await compose.compose_action(operation.resource, "up")
        else:
            await report("Applying stack action")
            if operation.action == "delete":
                await compose.delete_compose(operation.resource)
            else:
                await compose.compose_action(operation.resource, operation.action)
    elif operation.kind == "image.pull":
        from api.actions import resources
        await report("Pulling image")
        if operation.action == "update":
            await resources.update_image(operation.resource)
        else:
            await resources.write_image(operation.resource)


def _safe_failure(exc):
    if isinstance(exc, HTTPException):
        status = exc.status_code
        if status in (401, 403):
            return "The account no longer has permission for this operation.", status
        if status == 404:
            return "The requested resource no longer exists.", status
        if status == 409:
            return "The resource is busy or its state prevents this action.", status
    return "Operation failed. Check server logs for details.", 500


async def _execute(operation, runner):
    loop = asyncio.get_running_loop()
    limiter = _limiters.setdefault(loop, asyncio.Semaphore(MAX_CONCURRENT))
    try:
        async with limiter:
            actor = await _fresh_actor(operation)
            if operation.kind in BUILTIN_KINDS or operation.kind == "container.deploy":
                check_operation_permission(actor, operation.kind, operation.action)
            await _write_status(operation.id, status="running", phase="Starting", started_at=_utcnow())

            async def report(phase):
                if not isinstance(phase, str) or len(phase) > 120:
                    raise ValueError("Operation phase must be a short non-sensitive message")
                await _write_status(operation.id, phase=phase)

            result = await (runner(report) if runner else _builtin_runner(operation, report))
            await _write_status(operation.id, status="succeeded", phase="Completed", finished_at=_utcnow())
            async with SessionLocal() as db:
                await log_activity(db, operation.actor, "operation.succeeded", operation.resource, operation.kind)
            return Outcome(result=result)
    except asyncio.CancelledError:
        await _write_status(operation.id, status="interrupted", phase="Interrupted", finished_at=_utcnow(),
                            error="The service stopped before this operation finished. Verify the resource state before retrying.")
        raise
    except UnverifiedRestart:
        message = "A YachtPlus restart was requested. Reconnect and verify its state before retrying."
        await _write_status(operation.id, status="interrupted", phase="Restart requested", error=message, finished_at=_utcnow())
        return Outcome(error=message, status_code=409)
    except Exception as exc:
        message, code = _safe_failure(exc)
        logger.exception("Operation %s failed (kind=%s)", operation.id, operation.kind)
        await _write_status(operation.id, status="failed", phase="Failed", error=message, finished_at=_utcnow())
        return Outcome(error=message, status_code=code)


async def submit_operation(db, *, kind, resource, actor, action=None, runner=None, before_commit=None):
    """Commit and enqueue work; only code-owned closures may supply a runner.

    Callers must authorize the operation before submitting. Account identity and
    built-in permissions are checked again when a worker becomes available.
    """
    if not actor or not actor.is_active or (actor.id != 0 and not actor.account_instance):
        raise HTTPException(401, "User account is unavailable")
    if runner is None:
        validate_descriptor(kind, resource, action)
        check_operation_permission(actor, kind, action)
    elif not isinstance(kind, str) or len(kind) > 64 or not isinstance(resource, str) or len(resource) > 512:
        raise HTTPException(422, "Invalid operation descriptor")
    async with _loop_lock():
        active = sum(not task.done() for task in _tasks.values())
        if active >= MAX_PENDING:
            raise HTTPException(429, "The task queue is full. Try again after an operation finishes.")
        operation = Operation(kind=kind, resource=resource, action=action, actor=actor.username,
                              actor_id=actor.id, auth_version=actor.auth_version,
                              actor_instance=actor.account_instance or ("development" if actor.id == 0 else ""),
                              retry_supported=runner is None,
                              worker_id=_worker_id, heartbeat_at=_utcnow(),
                              status="queued", phase="Waiting for a worker")
        db.add(operation)
        try:
            await db.flush()
            if before_commit:
                before_commit(operation)
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        task = asyncio.create_task(_execute(operation, runner), name="operation-" + operation.id)
        _tasks[operation.id] = task
        task.add_done_callback(lambda completed: _tasks.pop(operation.id, None))
        return operation


async def wait_for_operation(operation_id):
    """Await a just-submitted task without cancelling it on caller disconnect."""
    task = _tasks.get(operation_id)
    if task is None:
        # A completed task's raw result deliberately has no persistent cache.
        async with SessionLocal() as db:
            operation = await db.get(Operation, operation_id)
        if not operation or operation.status != "succeeded":
            raise HTTPException(409, "Operation is not running in this worker")
        return None
    outcome = await asyncio.shield(task)
    if outcome.error:
        raise HTTPException(outcome.status_code, outcome.error)
    return outcome.result


async def start_operation_service():
    global _operation_loop, _heartbeat_task, _worker_id, _worker_pid
    if _worker_pid != os.getpid():
        # A preloaded multiworker server may import this module before fork.
        _worker_id = str(uuid.uuid4())
        _worker_pid = os.getpid()
    _operation_loop = asyncio.get_running_loop()
    await _expire_operations()
    if _heartbeat_task is None or _heartbeat_task.done():
        _heartbeat_task = asyncio.create_task(_heartbeat(), name="operation-heartbeat")


def get_operation_loop():
    """Scheduler threads submit coroutines to the application's existing loop."""
    return _operation_loop


async def _expire_operations():
    async with SessionLocal() as db:
        await db.execute(update(Operation).where(
            Operation.status.in_(ACTIVE_STATUSES),
            Operation.heartbeat_at < _utcnow() - timedelta(seconds=LEASE_SECONDS),
        ).values(
            status="interrupted", phase="Interrupted", finished_at=_utcnow(),
            error="The service restarted before this operation finished. Verify the resource state before retrying."))
        await db.commit()


async def _heartbeat():
    while True:
        try:
            async with SessionLocal() as db:
                await db.execute(update(Operation).where(
                    Operation.worker_id == _worker_id,
                    Operation.status.in_(ACTIVE_STATUSES),
                ).values(heartbeat_at=_utcnow()))
                await db.commit()
            await _expire_operations()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Could not refresh operation worker lease")
        await asyncio.sleep(5)


async def stop_operation_service():
    global _heartbeat_task, _operation_loop
    tasks = [task for task in _tasks.values() if not task.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _tasks.clear()
    if _heartbeat_task:
        _heartbeat_task.cancel()
        await asyncio.gather(_heartbeat_task, return_exceptions=True)
        _heartbeat_task = None
    _operation_loop = None
    _limiters.clear()
    _submit_locks.clear()
