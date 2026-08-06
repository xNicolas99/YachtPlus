"""Regression for BUG-002: /refresh blindly minted a new token from the
JWT subject without checking the user still exists or is active.
"""
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException, Request

from api.db.models.users import User

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from api.db.database import Base
import pytest_asyncio

from api.routers.users import refresh, limiter


@pytest.fixture(autouse=True)
def disable_rate_limit(monkeypatch):
    # slowapi rejects non-Request positional args; bypass the limiter for
    # these tests so we exercise the user-validation logic directly.
    monkeypatch.setattr(limiter, "enabled", False)


def _make_request():
    return MagicMock(spec=Request)


engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
TestingSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autocommit=False, autoflush=False)


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSessionLocal() as session:
        yield session


class MockAuth:
    def __init__(self, username, jwt_ok=True):
        self.username = username
        self.jwt_ok = jwt_ok
        self.unset_jwt_cookies = MagicMock()
        self.set_access_cookies = MagicMock()

    async def jwt_required(self, allow_setup_pending=False):
        if not self.jwt_ok:
            raise HTTPException(status_code=401, detail="Bad token")
        return True

    async def get_jwt_subject(self, allow_setup_pending=False):
        return self.username


@pytest.fixture(autouse=True)
def enable_auth(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


async def _user(db, username, **fields):
    defaults = dict(hashed_password="pw", is_active=True, is_superuser=False)
    defaults.update(fields)
    u = User(username=username, **defaults)
    db.add(u)
    await db.commit()
    return u


@pytest.mark.asyncio
async def test_refresh_for_unknown_user_fails(db):
    request = _make_request()
    response = MagicMock()
    auth = MockAuth("ghost")
    with pytest.raises(HTTPException) as exc:
        await refresh(request=request, response=response, db=db, Authorize=auth)
    assert exc.value.status_code == 401
    auth.unset_jwt_cookies.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_for_inactive_user_fails(db):
    await _user(db, "frozen", is_active=False)
    request = _make_request()
    response = MagicMock()
    auth = MockAuth("frozen")
    with pytest.raises(HTTPException) as exc:
        await refresh(request=request, response=response, db=db, Authorize=auth)
    assert exc.value.status_code == 401
    auth.unset_jwt_cookies.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_for_active_user_succeeds(db):
    await _user(db, "alice")
    request = _make_request()
    response = MagicMock()
    auth = MockAuth("alice")
    result = await refresh(request=request, response=response, db=db, Authorize=auth)
    assert result["refresh"] == "successful"
    auth.set_access_cookies.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_with_invalid_jwt_fails(db):
    await _user(db, "alice")
    request = _make_request()
    response = MagicMock()
    auth = MockAuth("alice", jwt_ok=False)
    with pytest.raises(HTTPException) as exc:
        await refresh(request=request, response=response, db=db, Authorize=auth)
    assert exc.value.status_code == 401
