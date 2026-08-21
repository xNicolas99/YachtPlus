"""Authorization tests for the container_exec WebSocket endpoint."""
import jwt as _jwt
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
import pytest_asyncio

from api.db.database import Base
from api.db.models.users import User
from api.routers.containers import container_exec_websocket


engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

SECRET = "test-secret-key-for-ws-authz-32bytes-minimum-length"


@pytest_asyncio.fixture
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    # The container_exec endpoint constructs its own DB session via
    # SessionLocal. Patch it to use the in-memory engine for the duration
    # of the test.
    with patch("api.routers.containers.SessionLocal", SessionLocal):
        async with SessionLocal() as session:
            yield session


@pytest.fixture(autouse=True)
def enable_auth(monkeypatch):
    monkeypatch.setattr("api.routers.containers.settings.DISABLE_AUTH", False)
    monkeypatch.setattr("api.routers.containers.get_secret_key", lambda: SECRET)


async def _add_user(db, username, **kw):
    defaults = dict(
        hashed_password="pw",
        is_active=True,
        is_superuser=False,
        perm_start=False,
        perm_stop=False,
        perm_restart=False,
        perm_delete=False,
    )
    defaults.update(kw)
    u = User(username=username, **defaults)
    db.add(u)
    await db.commit()
    return u


def _make_ws(token=None):
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    ws.cookies = {"access_token_cookie": token} if token else {}
    return ws


def _token(payload):
    return _jwt.encode(payload, SECRET, algorithm="HS256")


@pytest.mark.asyncio
async def test_ws_exec_rejects_missing_token(setup_db):
    ws = _make_ws(token=None)
    await container_exec_websocket(ws, "any", shell="/bin/sh")
    ws.send_json.assert_awaited_with({"error": "Unauthorized"})
    ws.close.assert_awaited_with(code=1008)


@pytest.mark.asyncio
async def test_ws_exec_rejects_invalid_signature(setup_db):
    ws = _make_ws(token=_jwt.encode({"sub": "anyone"}, "wrong-secret-32bytes-minimum-length", algorithm="HS256"))
    await container_exec_websocket(ws, "any", shell="/bin/sh")
    ws.send_json.assert_awaited_with({"error": "Unauthorized"})


@pytest.mark.asyncio
async def test_ws_exec_rejects_setup_pending_token(setup_db):
    await _add_user(setup_db, "admin", is_superuser=True)
    token = _token({"sub": "admin", "setup_pending": True})
    ws = _make_ws(token=token)
    await container_exec_websocket(ws, "any", shell="/bin/sh")
    ws.send_json.assert_awaited_with({"error": "Forbidden: setup not completed"})
    ws.close.assert_awaited_with(code=1008)


@pytest.mark.asyncio
async def test_ws_exec_rejects_unknown_user(setup_db):
    token = _token({"sub": "ghost"})
    ws = _make_ws(token=token)
    await container_exec_websocket(ws, "any", shell="/bin/sh")
    ws.send_json.assert_awaited_with({"error": "Forbidden"})


@pytest.mark.asyncio
async def test_ws_exec_rejects_inactive_user(setup_db):
    await _add_user(setup_db, "inactive", is_active=False, perm_start=True)
    token = _token({"sub": "inactive"})
    ws = _make_ws(token=token)
    await container_exec_websocket(ws, "any", shell="/bin/sh")
    ws.send_json.assert_awaited_with({"error": "Forbidden"})


@pytest.mark.asyncio
async def test_ws_exec_rejects_user_without_perm_start(setup_db):
    await _add_user(setup_db, "noperm")
    token = _token({"sub": "noperm"})
    ws = _make_ws(token=token)
    await container_exec_websocket(ws, "any", shell="/bin/sh")
    ws.send_json.assert_awaited_with({"error": "Forbidden: missing permission"})


@pytest.mark.asyncio
async def test_ws_exec_permits_authorised_user(setup_db, monkeypatch):
    await _add_user(setup_db, "ops", perm_start=True)
    from api.routers import containers as _containers_module
    object.__setattr__(_containers_module.settings, "DOCKER_HOST", "unix:///var/run/docker.sock")
    token = _token({"sub": "ops"})
    ws = _make_ws(token=token)
    ws.receive = AsyncMock(side_effect=Exception("stop test loop"))

    # Mock aiodocker so we don't actually try to connect.
    docker_instance = MagicMock()
    docker_instance.containers = MagicMock()
    docker_instance.containers.get = AsyncMock(side_effect=Exception("container not found"))
    docker_instance.close = AsyncMock()
    with patch("api.routers.containers.aiodocker.Docker", return_value=docker_instance):
        await container_exec_websocket(ws, "abc", shell="/bin/sh")

    # We should NOT have been blocked at the authz step. Verify by checking
    # that no Unauthorized/Forbidden was emitted before the container lookup.
    payloads = [c.args[0] for c in ws.send_json.await_args_list]
    for p in payloads:
        assert p.get("error") not in {
            "Unauthorized",
            "Forbidden",
            "Forbidden: setup not completed",
            "Forbidden: missing permission",
        }, f"authz unexpectedly rejected: {p}"


@pytest.mark.asyncio
async def test_ws_exec_superuser_bypasses_perm(setup_db, monkeypatch):
    await _add_user(setup_db, "root", is_superuser=True)
    from api.routers import containers as _containers_module
    object.__setattr__(_containers_module.settings, "DOCKER_HOST", "unix:///var/run/docker.sock")
    token = _token({"sub": "root"})
    ws = _make_ws(token=token)
    ws.receive = AsyncMock(side_effect=Exception("stop test loop"))

    docker_instance = MagicMock()
    docker_instance.containers = MagicMock()
    docker_instance.containers.get = AsyncMock(side_effect=Exception("not found"))
    docker_instance.close = AsyncMock()
    with patch("api.routers.containers.aiodocker.Docker", return_value=docker_instance):
        await container_exec_websocket(ws, "abc", shell="/bin/sh")

    # No authz error should have been sent for a superuser.
    payloads = [c.args[0] for c in ws.send_json.await_args_list]
    for p in payloads:
        assert p.get("error") not in {
            "Unauthorized",
            "Forbidden",
            "Forbidden: setup not completed",
            "Forbidden: missing permission",
        }, f"authz unexpectedly rejected superuser: {p}"


@pytest.mark.asyncio
async def test_ws_exec_skips_auth_when_disabled(setup_db, monkeypatch):
    monkeypatch.setattr("api.routers.containers.settings.DISABLE_AUTH", True)
    from api.routers import containers as _containers_module
    object.__setattr__(_containers_module.settings, "DOCKER_HOST", "unix:///var/run/docker.sock")
    ws = _make_ws(token=None)
    ws.receive = AsyncMock(side_effect=Exception("stop test loop"))

    docker_instance = MagicMock()
    docker_instance.containers = MagicMock()
    docker_instance.containers.get = AsyncMock(side_effect=Exception("not found"))
    docker_instance.close = AsyncMock()
    with patch("api.routers.containers.aiodocker.Docker", return_value=docker_instance):
        await container_exec_websocket(ws, "abc", shell="/bin/sh")

    # When auth is disabled we should not see any Unauthorized/Forbidden messages.
    payloads = [c.args[0] for c in ws.send_json.await_args_list]
    for p in payloads:
        assert p.get("error") not in {
            "Unauthorized",
            "Forbidden",
            "Forbidden: setup not completed",
            "Forbidden: missing permission",
        }
