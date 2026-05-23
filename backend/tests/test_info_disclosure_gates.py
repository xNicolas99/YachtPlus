"""Regression for BUG-003 + BUG-004.

Sensitive endpoints that previously only ran auth_check are now gated:
- compose /{project}/support  -> superuser
- apps /{app}/support         -> superuser
- apps /{app}/logs            -> perm_start
- apps /{app}/processes       -> perm_start
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from api.db.database import Base
from api.db.models.users import User
from api.routers.compose import get_support_bundle as compose_support_bundle
from api.routers.apps import (
    get_support_bundle as apps_support_bundle,
    get_container_processes,
    logs as apps_logs,
)


engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    yield s
    s.close()


class MockAuth:
    def __init__(self, username):
        self.username = username

    def jwt_required(self, allow_setup_pending=False):
        return True

    def get_jwt_subject(self, allow_setup_pending=False):
        return self.username


@pytest.fixture(autouse=True)
def enable_auth(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


def _add(db, username, **fields):
    defaults = dict(
        hashed_password="pw",
        is_active=True,
        is_superuser=False,
        perm_start=False,
        perm_stop=False,
        perm_restart=False,
        perm_delete=False,
    )
    defaults.update(fields)
    u = User(username=username, **defaults)
    db.add(u)
    db.commit()
    return u


# --- compose support bundle -------------------------------------------------

@pytest.mark.asyncio
async def test_compose_support_rejects_non_superuser(db):
    _add(db, "ops", perm_start=True, perm_stop=True, perm_restart=True, perm_delete=True)
    with pytest.raises(HTTPException) as exc:
        await compose_support_bundle("demo", Authorize=MockAuth("ops"), db=db)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_compose_support_allows_superuser(db):
    _add(db, "root", is_superuser=True)
    with patch(
        "api.routers.compose.generate_support_bundle",
        new=AsyncMock(return_value=b"ZIP"),
    ):
        result = await compose_support_bundle("demo", Authorize=MockAuth("root"), db=db)
    assert result == b"ZIP"


# --- apps support bundle ----------------------------------------------------

@pytest.mark.asyncio
async def test_apps_support_rejects_perm_start_user(db):
    """Even perm_start isn't enough — support bundles include env vars."""
    _add(db, "ops", perm_start=True)
    with pytest.raises(HTTPException) as exc:
        await apps_support_bundle("app", Authorize=MockAuth("ops"), db=db)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_apps_support_allows_superuser(db):
    _add(db, "root", is_superuser=True)
    with patch(
        "api.routers.apps.actions.generate_support_bundle",
        new=AsyncMock(return_value=b"BUNDLE"),
    ):
        result = await apps_support_bundle("app", Authorize=MockAuth("root"), db=db)
    assert result == b"BUNDLE"


# --- apps processes ---------------------------------------------------------

@pytest.mark.asyncio
async def test_apps_processes_rejects_user_without_perm_start(db):
    _add(db, "noperm")
    with pytest.raises(HTTPException) as exc:
        await get_container_processes("app", Authorize=MockAuth("noperm"), db=db)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_apps_processes_allows_perm_start(db):
    _add(db, "ops", perm_start=True)
    with patch(
        "api.routers.apps.actions.get_app_processes",
        new=AsyncMock(return_value={"Titles": [], "Processes": []}),
    ):
        result = await get_container_processes("app", Authorize=MockAuth("ops"), db=db)
    assert "Processes" in result


# --- apps logs --------------------------------------------------------------

@pytest.mark.asyncio
async def test_apps_logs_rejects_user_without_perm_start(db):
    _add(db, "noperm")
    request = MagicMock()
    with pytest.raises(HTTPException) as exc:
        await apps_logs("app", request, Authorize=MockAuth("noperm"), db=db)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_apps_logs_allows_perm_start(db):
    _add(db, "ops", perm_start=True)
    request = MagicMock()
    with patch("api.routers.apps.actions.log_generator", return_value=MagicMock()):
        result = await apps_logs("app", request, Authorize=MockAuth("ops"), db=db)
    # EventSourceResponse object — just confirm we got one back.
    assert result is not None
