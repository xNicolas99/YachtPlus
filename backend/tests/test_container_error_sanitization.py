"""Regression for BUG-007/008/009: container action handlers were
echoing the raw exception message back to the client via the HTTP
detail field (start/stop/restart/delete) or via the WebSocket close
reason (exec). That leaked internal docker-daemon details (file paths,
container IDs, capability hints, error backtrace fragments) into the
response body of every failure. Additionally, "no such container" used
to map to 500 instead of 404, making it impossible for the frontend to
react cleanly. The fix sanitizes details to fixed strings, propagates
the daemon's status code where appropriate, and keeps the full diagnostic
in the server log only.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from aiodocker.exceptions import DockerError

from api.routers.containers import (
    start_container,
    stop_container,
    restart_container,
    delete_container,
)


class MockAuth:
    async def jwt_required(self, allow_setup_pending=False):
        return True

    async def get_jwt_subject(self, allow_setup_pending=False):
        return "admin"


@pytest.fixture(autouse=True)
def _force_auth_on(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


@pytest.fixture
def docker_host(monkeypatch):
    from api.routers import containers as containers_module
    from api.settings import Settings
    original = containers_module.settings
    monkeypatch.setattr(
        containers_module,
        "settings",
        Settings(DOCKER_HOST="unix:///var/run/docker.sock"),
    )
    yield
    monkeypatch.setattr(containers_module, "settings", original)


def _patch_docker(container_mock):
    docker_instance = MagicMock()
    docker_instance.containers = MagicMock()
    docker_instance.containers.get = AsyncMock(return_value=container_mock)
    docker_instance.close = AsyncMock()
    return patch(
        "api.routers.containers.aiodocker.Docker",
        return_value=docker_instance,
    ), docker_instance


SECRET_ID = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"


@pytest.mark.asyncio
async def test_start_container_does_not_leak_exception_message(db, docker_host):
    container = MagicMock()
    container.start = AsyncMock(side_effect=Exception(f"OCI runtime exec failed: {SECRET_ID}"))
    patcher, _ = _patch_docker(container)
    with patcher, pytest.raises(HTTPException) as exc:
        await start_container(MagicMock(), "abc", db=db, Authorize=MockAuth())
    assert exc.value.status_code == 500
    assert SECRET_ID not in str(exc.value.detail)
    assert exc.value.detail == "Internal error"


@pytest.mark.asyncio
async def test_start_container_propagates_docker_404(db, docker_host):
    container = MagicMock()
    err = DockerError(404, {"message": f"No such container: {SECRET_ID}"})
    container.start = AsyncMock(side_effect=err)
    patcher, _ = _patch_docker(container)
    with patcher, pytest.raises(HTTPException) as exc:
        await start_container(MagicMock(), "abc", db=db, Authorize=MockAuth())
    assert exc.value.status_code == 404
    assert SECRET_ID not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_stop_container_sanitizes_detail(db, docker_host):
    container = MagicMock()
    container.stop = AsyncMock(side_effect=Exception(f"path: /var/lib/docker/{SECRET_ID}"))
    patcher, _ = _patch_docker(container)
    with patcher, pytest.raises(HTTPException) as exc:
        await stop_container(MagicMock(), "c", db=db, Authorize=MockAuth())
    assert SECRET_ID not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_restart_container_sanitizes_detail(db, docker_host):
    container = MagicMock()
    container.restart = AsyncMock(side_effect=Exception(SECRET_ID))
    patcher, _ = _patch_docker(container)
    with patcher, pytest.raises(HTTPException) as exc:
        await restart_container(MagicMock(), "c", db=db, Authorize=MockAuth())
    assert SECRET_ID not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_delete_container_returns_404_when_missing(db, docker_host):
    container = MagicMock()
    err = DockerError(404, {"message": "No such container: ghost"})
    container.delete = AsyncMock(side_effect=err)
    patcher, _ = _patch_docker(container)
    with patcher, pytest.raises(HTTPException) as exc:
        await delete_container(MagicMock(), "ghost", db=db, Authorize=MockAuth())
    assert exc.value.status_code == 404
    assert exc.value.detail == "Container not found"


@pytest.mark.asyncio
async def test_delete_container_sanitizes_on_unexpected_error(db, docker_host):
    container = MagicMock()
    container.delete = AsyncMock(side_effect=RuntimeError(SECRET_ID))
    patcher, _ = _patch_docker(container)
    with patcher, pytest.raises(HTTPException) as exc:
        await delete_container(MagicMock(), "dead", db=db, Authorize=MockAuth())
    assert exc.value.status_code == 500
    assert SECRET_ID not in str(exc.value.detail)
