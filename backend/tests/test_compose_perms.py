"""Permission enforcement tests for the compose router.

The compose router previously only called auth_check; users without
perm_start/perm_stop/perm_restart/perm_delete could trigger destructive
actions through it. These tests pin the permission gates in place.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException

from api.db.database import Base
from api.db.models.users import User
from api.routers.compose import compose_project_action as get_compose_action, compose_app_action_route as get_compose_app_action


engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        yield session


class MockAuth:
    def __init__(self, username):
        self.username = username

    async def jwt_required(self, allow_setup_pending=False):
        return True

    async def get_jwt_subject(self, allow_setup_pending=False):
        return self.username


@pytest.fixture(autouse=True)
def enable_auth(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


async def _add(db, username, **perms):
    defaults = dict(
        hashed_password="pw",
        is_active=True,
        is_superuser=False,
        perm_start=False,
        perm_stop=False,
        perm_restart=False,
        perm_delete=False,
    )
    defaults.update(perms)
    user = User(username=username, **defaults)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_compose_start_requires_perm_start(db):
    await _add(db, "noperm")

    with pytest.raises(HTTPException) as exc:
        await get_compose_action(
            project_name="demo",
            action="start",
            Authorize=MockAuth("noperm"),
            db=db,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_compose_start_succeeds_with_perm_start(db):
    await _add(db, "starter", perm_start=True)

    with patch(
        "api.routers.compose.compose_action",
        new=AsyncMock(return_value={"ok": True}),
    ) as ca:
        result = await get_compose_action(
            project_name="demo",
            action="start",
            Authorize=MockAuth("starter"),
            db=db,
        )

    assert result == {"ok": True}
    ca.assert_awaited_once_with("demo", "start")


@pytest.mark.asyncio
async def test_compose_stop_requires_perm_stop(db):
    await _add(db, "starter_only", perm_start=True)

    with pytest.raises(HTTPException) as exc:
        await get_compose_action(
            project_name="demo",
            action="stop",
            Authorize=MockAuth("starter_only"),
            db=db,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_compose_delete_requires_perm_delete(db):
    await _add(db, "no_delete", perm_start=True, perm_stop=True, perm_restart=True)

    with pytest.raises(HTTPException) as exc:
        await get_compose_action(
            project_name="demo",
            action="delete",
            Authorize=MockAuth("no_delete"),
            db=db,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_compose_delete_with_perm_delete(db):
    await _add(db, "deleter", perm_delete=True)

    with patch(
        "api.routers.compose.delete_compose",
        new=AsyncMock(return_value={"deleted": True}),
    ) as dc:
        result = await get_compose_action(
            project_name="demo",
            action="delete",
            Authorize=MockAuth("deleter"),
            db=db,
        )
    assert result == {"deleted": True}
    dc.assert_awaited_once_with("demo")


@pytest.mark.asyncio
async def test_compose_pull_does_not_require_action_perm(db):
    """`pull` only fetches images; no run-state mutation, so no perm gate."""
    await _add(db, "puller")

    with patch(
        "api.routers.compose.compose_action",
        new=AsyncMock(return_value={"pulled": True}),
    ):
        result = await get_compose_action(
            project_name="demo",
            action="pull",
            Authorize=MockAuth("puller"),
            db=db,
        )
    assert result == {"pulled": True}


@pytest.mark.asyncio
async def test_compose_invalid_action_returns_400(db):
    await _add(db, "anyone", perm_start=True, perm_stop=True, perm_restart=True, perm_delete=True)

    with pytest.raises(HTTPException) as exc:
        await get_compose_action(
            project_name="demo",
            action="nuke",
            Authorize=MockAuth("anyone"),
            db=db,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_compose_app_action_requires_matching_perm(db):
    await _add(db, "starter", perm_start=True)

    # `rm` requires perm_delete, which `starter` lacks.
    with pytest.raises(HTTPException) as exc:
        await get_compose_app_action(
            project_name="demo",
            action="rm",
            app="svc",
            Authorize=MockAuth("starter"),
            db=db,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_compose_app_action_passes_through_when_authorised(db):
    await _add(db, "ops", perm_restart=True)

    with patch(
        "api.routers.compose.compose_app_action",
        new=AsyncMock(return_value={"restarted": True}),
    ) as caa:
        result = await get_compose_app_action(
            project_name="demo",
            action="restart",
            app="svc",
            Authorize=MockAuth("ops"),
            db=db,
        )
    assert result == {"restarted": True}
    caa.assert_awaited_once_with("demo", "restart", "svc")


@pytest.mark.asyncio
async def test_superuser_bypasses_perm_check(db):
    await _add(db, "root", is_superuser=True)

    with patch(
        "api.routers.compose.delete_compose",
        new=AsyncMock(return_value={"deleted": True}),
    ):
        result = await get_compose_action(
            project_name="demo",
            action="delete",
            Authorize=MockAuth("root"),
            db=db,
        )
    assert result == {"deleted": True}
