"""B-09: deleted or disabled API keys must be rejected immediately."""

import pytest
import pytest_asyncio
from datetime import timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from api.auth.jwt import _is_api_key_active, create_access_token, get_secret_key
from api.db.database import Base
from api.db.models.users import User, APIKEY
from api.db.crud import users as users_crud
import jwt as _pyjwt


engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def _shared_db(monkeypatch):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    import api.db.database as db_mod
    monkeypatch.setattr(db_mod, "SessionLocal", SessionLocal)
    yield


@pytest_asyncio.fixture
async def user():
    async with SessionLocal() as db:
        u = User(username="api-active@example.com", hashed_password="x", is_active=True)
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u


@pytest.mark.asyncio
async def test_is_api_key_active_missing():
    assert await _is_api_key_active("nonexistent-jti") is False


@pytest.mark.asyncio
async def test_api_key_token_requires_active_record(user):
    async with SessionLocal() as db:
        result = await users_crud.create_key("active-key", user, None, db)
        token = result["token"]
        decoded = _pyjwt.decode(token, get_secret_key(), algorithms=["HS256"])
        # Soft-delete the record (simulate blacklist/delete without blacklisting jti)
        key_id = result["id"]
        key = await db.get(APIKEY, key_id)
        await db.delete(key)
        await db.commit()

        # After deletion the JTI is gone -> _is_api_key_active is False
        assert await _is_api_key_active(decoded["jti"]) is False


@pytest.mark.asyncio
async def test_disabled_api_key_rejected(user):
    async with SessionLocal() as db:
        result = await users_crud.create_key("disabled-key", user, None, db)
        token = result["token"]
        decoded = _pyjwt.decode(token, get_secret_key(), algorithms=["HS256"])
        key_id = result["id"]
        key = await db.get(APIKEY, key_id)
        key.is_active = False
        await db.commit()

        assert await _is_api_key_active(decoded["jti"]) is False
