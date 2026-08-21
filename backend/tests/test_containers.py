import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from api.db.database import Base
from api.routers.containers import (
    list_containers as get_containers,
    get_container_logs,
    get_container_stats,
    start_container,
    stop_container,
    restart_container,
    delete_container,
)
from api.utils.auth import get_db


engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


class MockAuthValid:
    def __init__(self, user="admin"):
        self.user = user

    async def jwt_required(self, allow_setup_pending=False):
        return True

    async def get_jwt_subject(self, allow_setup_pending=False):
        return self.user


class MockAuthInvalid:
    async def jwt_required(self, allow_setup_pending=False):
        raise HTTPException(status_code=401, detail="Unauthorized")

    async def get_jwt_subject(self, allow_setup_pending=False):
        raise HTTPException(status_code=401, detail="Unauthorized")


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def mock_auth_enabled(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


@pytest.fixture
def mock_docker_host(monkeypatch):
    # Ensure settings has a DOCKER_HOST value while the test runs.
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


@pytest.mark.asyncio
async def test_get_db_dependency_yields_and_closes():
    from sqlalchemy.ext.asyncio import AsyncSession
    db_gen = get_db()
    session = await anext(db_gen)
    assert isinstance(session, AsyncSession)
    with pytest.raises(StopAsyncIteration):
        await anext(db_gen)


@pytest.mark.asyncio
async def test_get_containers_returns_list(mock_auth_enabled):
    expected = [{"Id": "1", "Names": ["/c1"]}]
    with patch(
        "api.routers.containers.actions.get_containers",
        new=AsyncMock(return_value=expected),
    ):
        result = await get_containers(MagicMock(), Authorize=MockAuthValid(), db=MagicMock())
    assert result == expected


@pytest.mark.asyncio
async def test_get_containers_unauthorized(mock_auth_enabled):
    with pytest.raises(HTTPException) as exc:
        await get_containers(MagicMock(), Authorize=MockAuthInvalid(), db=MagicMock())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_get_container_stats_returns_action_result(mock_auth_enabled):
    expected = {"cpu": 5.0, "ram": 10.0}
    request = MagicMock()
    request.query_params = {"stream": "false"}
    with patch(
        "api.routers.containers.actions.get_stats",
        new=AsyncMock(return_value=expected),
    ) as get_stats:
        result = await get_container_stats(
            request=request,
            container_id="abc",
            Authorize=MockAuthValid(),
            db=MagicMock(),
        )

    assert result == expected
    get_stats.assert_awaited_once_with("abc")


def _patch_docker(container_mock):
    """Build a context manager that patches aiodocker.Docker.

    The returned Docker instance has .containers.get awaitable returning
    container_mock and .close awaitable.
    """
    docker_instance = MagicMock()
    docker_instance.containers = MagicMock()
    docker_instance.containers.get = AsyncMock(return_value=container_mock)
    docker_instance.close = AsyncMock()
    return patch(
        "api.routers.containers.aiodocker.Docker",
        return_value=docker_instance,
    ), docker_instance


@pytest.mark.asyncio
async def test_start_container_logs_activity_and_returns_message(db, mock_auth_enabled):
    container = MagicMock()
    container.start = AsyncMock()
    patcher, docker_instance = _patch_docker(container)
    with patcher, patch("api.routers.containers.log_activity") as log:
        result = await start_container(MagicMock(), "abc", db=db, Authorize=MockAuthValid("u1"))

    assert result == {"message": "Container started"}
    container.start.assert_awaited_once()
    log.assert_called_once_with(db, "u1", "start", "abc")
    docker_instance.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_container_handles_docker_error(db, mock_auth_enabled):
    container = MagicMock()
    container.start = AsyncMock(side_effect=Exception("boom"))
    patcher, docker_instance = _patch_docker(container)
    with patcher, pytest.raises(HTTPException) as exc:
        await start_container(MagicMock(), "abc", db=db, Authorize=MockAuthValid())

    assert exc.value.status_code == 500
    # The raw exception message is intentionally NOT echoed back to the
    # caller (would leak daemon internals) — only a sanitized detail.
    assert "boom" not in exc.value.detail
    assert exc.value.detail in ("Internal error", "Failed to start container")
    docker_instance.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_container_logs_activity(db, mock_auth_enabled):
    container = MagicMock()
    container.stop = AsyncMock()
    patcher, docker_instance = _patch_docker(container)
    with patcher, patch("api.routers.containers.log_activity") as log:
        result = await stop_container(MagicMock(), "xyz", db=db, Authorize=MockAuthValid("u2"))

    assert result == {"message": "Container stopped"}
    container.stop.assert_awaited_once()
    log.assert_called_once_with(db, "u2", "stop", "xyz")


@pytest.mark.asyncio
async def test_stop_container_handles_error(db, mock_auth_enabled):
    container = MagicMock()
    container.stop = AsyncMock(side_effect=Exception("nope"))
    patcher, _ = _patch_docker(container)
    with patcher, pytest.raises(HTTPException) as exc:
        await stop_container(MagicMock(), "xyz", db=db, Authorize=MockAuthValid())
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_restart_container_success(db, mock_auth_enabled):
    container = MagicMock()
    container.restart = AsyncMock()
    patcher, _ = _patch_docker(container)
    with patcher, patch("api.routers.containers.log_activity") as log:
        result = await restart_container(MagicMock(), "c1", db=db, Authorize=MockAuthValid("u3"))

    assert result == {"message": "Container restarted"}
    container.restart.assert_awaited_once()
    log.assert_called_once_with(db, "u3", "restart", "c1")


@pytest.mark.asyncio
async def test_restart_container_handles_error(db, mock_auth_enabled):
    container = MagicMock()
    container.restart = AsyncMock(side_effect=Exception("fail"))
    patcher, _ = _patch_docker(container)
    with patcher, pytest.raises(HTTPException) as exc:
        await restart_container(MagicMock(), "c1", db=db, Authorize=MockAuthValid())
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_delete_container_success(db, mock_auth_enabled):
    container = MagicMock()
    container.delete = AsyncMock()
    patcher, _ = _patch_docker(container)
    with patcher, patch("api.routers.containers.log_activity") as log:
        result = await delete_container(MagicMock(), "dead", db=db, Authorize=MockAuthValid("u4"))

    assert result == {"message": "Container deleted"}
    container.delete.assert_awaited_once_with(force=True)
    log.assert_called_once_with(db, "u4", "delete", "dead")


@pytest.mark.asyncio
async def test_delete_container_handles_error(db, mock_auth_enabled):
    container = MagicMock()
    container.delete = AsyncMock(side_effect=Exception("err"))
    patcher, _ = _patch_docker(container)
    with patcher, pytest.raises(HTTPException) as exc:
        await delete_container(MagicMock(), "dead", db=db, Authorize=MockAuthValid())
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_start_container_unauthorized(db, mock_auth_enabled):
    with pytest.raises(HTTPException) as exc:
        await start_container(MagicMock(), "abc", db=db, Authorize=MockAuthInvalid())
    assert exc.value.status_code == 401
