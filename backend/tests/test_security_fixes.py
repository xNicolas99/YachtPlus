"""Regression tests for the security bug-fix batch:

- FIX 1: POST /api/auth/me must not allow self privilege escalation
         (perm_* / is_superuser / is_active are stripped from the payload).
- FIX 2: compute_cpu_percent tolerates missing precpu_stats/cpu_stats.
- FIX 3: pause/unpause are gated by perm_stop/perm_start respectively.
- FIX 4: GET /api/apps/{app_name} is gated by perm_start (env-secret leak).
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from api.db.database import Base
from api.db.models.users import User


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

    def is_api_key(self):
        return False


@pytest.fixture(autouse=True)
def enable_auth(monkeypatch):
    # Force the real check_permission path (not the DISABLE_AUTH shortcut).
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


async def _add_user(db, username, **perms):
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


# --- FIX 1: self privilege escalation -------------------------------------

@pytest.mark.asyncio
async def test_me_self_update_ignores_perm_delete(db):
    """A low-priv user POSTing {"perm_delete": true} to /auth/me must not
    end up with perm_delete set. The endpoint uses UserSelfUpdate, whose
    pydantic model drops the field entirely before reaching the CRUD."""
    from api.routers.users import update_user as me_update
    from api.db.crud.users import get_user_by_name

    await _add_user(db, "lowpriv")

    # Attacker crafts a body that tries to self-grant perm_delete. Pydantic
    # parses it into UserSelfUpdate, which has no such field -> ignored.
    from api.db.schemas.users import UserSelfUpdate
    payload = UserSelfUpdate.model_validate({"username": "lowpriv", "perm_delete": True})

    await me_update(
        user=payload,
        db=db,
        Authorize=MockAuth("lowpriv"),
        request=MagicMock(),
    )

    refreshed = await get_user_by_name(db, "lowpriv")
    assert refreshed.perm_delete is False
    assert refreshed.is_superuser is False


@pytest.mark.asyncio
async def test_me_self_update_ignores_is_superuser(db):
    """Same vector via is_superuser — must never be self-assignable."""
    from api.routers.users import update_user as me_update
    from api.db.crud.users import get_user_by_name
    from api.db.schemas.users import UserSelfUpdate

    await _add_user(db, "low2")
    payload = UserSelfUpdate.model_validate({"is_superuser": True, "is_active": True})

    await me_update(user=payload, db=db, Authorize=MockAuth("low2"), request=MagicMock())
    refreshed = await get_user_by_name(db, "low2")
    assert refreshed.is_superuser is False


# --- FIX 2: stats KeyError -------------------------------------------------

def test_compute_cpu_percent_missing_precpu_stats():
    """Freshly started containers ship no precpu_stats — must not KeyError."""
    from api.actions.containers import compute_cpu_percent

    stats = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 500},
            "system_cpu_usage": 5000,
            "online_cpus": 2,
        }
        # no precpu_stats at all
    }
    # system_delta = 5000 - 0 > 0, cpu_delta = 500 -> positive result
    result = compute_cpu_percent(stats)
    assert result >= 0.0


def test_compute_cpu_percent_empty_stats():
    from api.actions.containers import compute_cpu_percent

    assert compute_cpu_percent({}) == 0.0
    assert compute_cpu_percent({"cpu_stats": None, "precpu_stats": None}) == 0.0


def test_compute_cpu_percent_zero_system_delta():
    """Equal pre/current system usage -> delta 0 -> guard against /0."""
    from api.actions.containers import compute_cpu_percent

    stats = {
        "cpu_stats": {"cpu_usage": {"total_usage": 100}, "system_cpu_usage": 1000},
        "precpu_stats": {"cpu_usage": {"total_usage": 50}, "system_cpu_usage": 1000},
    }
    assert compute_cpu_percent(stats) == 0.0


# --- FIX 3: pause / unpause permission gates --------------------------------

@pytest.mark.asyncio
async def test_pause_requires_perm_stop(db):
    from api.routers.apps import container_actions

    await _add_user(db, "noperm", perm_start=True)

    with pytest.raises(HTTPException) as exc:
        await container_actions(
            app_name="demo",
            action="pause",
            background_tasks=MagicMock(),
            Authorize=MockAuth("noperm"),
            db=db,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_unpause_requires_perm_start(db):
    from api.routers.apps import container_actions

    await _add_user(db, "stopper", perm_stop=True, perm_restart=True)

    with pytest.raises(HTTPException) as exc:
        await container_actions(
            app_name="demo",
            action="unpause",
            background_tasks=MagicMock(),
            Authorize=MockAuth("stopper"),
            db=db,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_pause_allowed_with_perm_stop(db):
    from api.routers.apps import container_actions

    await _add_user(db, "pauser", perm_stop=True)

    with patch(
        "api.actions.apps.app_action", new=AsyncMock(return_value={"ok": True})
    ):
        result = await container_actions(
            app_name="demo",
            action="pause",
            background_tasks=MagicMock(),
            Authorize=MockAuth("pauser"),
            db=db,
        )
    assert result == {"ok": True}


# --- FIX 4: GET /apps/{name} perm_start gate --------------------------------

@pytest.mark.asyncio
async def test_get_app_requires_perm_start(db):
    from api.routers.apps import get_container_details

    await _add_user(db, "noperm")

    with pytest.raises(HTTPException) as exc:
        await get_container_details(
            app_name="demo",
            Authorize=MockAuth("noperm"),
            db=db,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_app_allowed_with_perm_start(db):
    from api.routers.apps import get_container_details

    await _add_user(db, "reader", perm_start=True)

    with patch(
        "api.actions.apps.get_app", new=AsyncMock(return_value={"name": "demo"})
    ) as ga:
        result = await get_container_details(
            app_name="demo",
            Authorize=MockAuth("reader"),
            db=db,
        )
    assert result == {"name": "demo"}
    ga.assert_awaited_once()
