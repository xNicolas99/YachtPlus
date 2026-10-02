"""Regression for BUG-001: POST /api/setup/bypass would brick a fresh
deployment. Any unauthenticated caller could flip SetupStatus.is_bypassed
to True on the FIRST request to a fresh instance, after which the setup
middleware stopped short-circuiting /api/* to 428 and every data router
fell through to auth_check — but no user existed, so nobody could ever
log in. The endpoint is now gated behind DISABLE_AUTH=True (dev only).
"""
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlalchemy import select, func

from api.db.database import Base
from api.routers.setup.setup import bypass_setup, is_setup_completed_async
from api.db.models.setup import SetupStatus


engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autocommit=False, autoflush=False)


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        yield s


def _settings_mock(disabled_auth: bool):
    fake = MagicMock()
    fake.DISABLE_AUTH = disabled_auth
    return fake


@pytest.mark.asyncio
async def test_bypass_rejected_in_production_mode(db):
    """The brick-DoS path. DISABLE_AUTH is the default False, so a hostile
    caller on a fresh install must get a 404 here."""
    with patch("api.routers.setup.setup.get_settings", return_value=_settings_mock(False)):
        with pytest.raises(HTTPException) as exc:
            await bypass_setup(db=db)
    assert exc.value.status_code == 404
    # Nothing should have been written to SetupStatus.
    count_result = await db.execute(select(func.count()).select_from(SetupStatus))
    assert count_result.scalar() == 0
    # is_setup_completed must still be False — the system is still
    # waiting for legit registration.
    assert await is_setup_completed_async(db) is False


@pytest.mark.asyncio
async def test_bypass_allowed_in_dev_mode(db):
    """In dev mode (DISABLE_AUTH=True) the bypass is intentional — it lets
    a developer skip the wizard on a throwaway DB."""
    with patch("api.routers.setup.setup.get_settings", return_value=_settings_mock(True)):
        result = await bypass_setup(db=db)
    assert "bypassed" in result["message"].lower()
    status_result = await db.execute(select(SetupStatus))
    status = status_result.scalars().first()
    assert status is not None
    assert status.is_bypassed is True


@pytest.mark.asyncio
async def test_bypass_still_refuses_after_user_exists(db):
    """Even in dev mode, refuse to bypass once a real user has been
    registered — that user would otherwise be silently kept active."""
    from api.db.models.users import User
    db.add(User(username="alice", hashed_password="pw"))
    await db.commit()

    with patch("api.routers.setup.setup.get_settings", return_value=_settings_mock(True)):
        with pytest.raises(HTTPException) as exc:
            await bypass_setup(db=db)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_bypass_returns_idempotent_message_when_already_completed(db):
    """Calling bypass a second time after legit completion should not
    rewrite the SetupStatus row — just return the no-op message."""
    db.add(SetupStatus(is_complete=True))
    await db.commit()

    with patch("api.routers.setup.setup.get_settings", return_value=_settings_mock(True)):
        result = await bypass_setup(db=db)
    assert "already" in result["message"].lower()
    status_result = await db.execute(select(SetupStatus))
    status = status_result.scalars().first()
    # is_complete stays True, is_bypassed not flipped.
    assert status.is_complete is True
    assert status.is_bypassed is not True  # accept False or None
