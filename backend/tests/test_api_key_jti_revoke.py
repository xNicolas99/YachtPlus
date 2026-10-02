"""Regression for FND-201 / FND-204: API keys must store their jti,
and revoking an API key must invalidate the underlying JWT immediately.

Without these fixes:
  - create_key stores jti=None even though the model declares it non-nullable.
  - blacklist_api_key only deletes the DB row, so the token stays valid
    for its full 10-year lifetime.
"""
import pytest
import pytest_asyncio
import jwt as _pyjwt
from datetime import timedelta, datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlalchemy import select

from api.db.database import Base
from api.db.models.users import User, APIKEY
from api.db.models.settings import TokenBlacklist
from api.db.crud import users as users_crud
from api.auth.jwt import get_secret_key, verify_token
from fastapi import HTTPException, status


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
async def user(db: AsyncSession):
    u = User(username="alice@example.com", hashed_password="x", is_active=True)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_create_key_stores_jti_and_expires():
    async with SessionLocal() as db:
        u = User(username="apiuser@example.com", hashed_password="x", is_active=True)
        db.add(u)
        await db.commit()
        await db.refresh(u)

        result = await users_crud.create_key("test-key", u, None, db)
        token = result["token"]
        decoded = _pyjwt.decode(token, get_secret_key(), algorithms=["HS256"])

        key_id = result["id"]
        res = await db.execute(select(APIKEY).filter(APIKEY.id == key_id))
        key = res.scalars().first()

        assert key.jti == decoded["jti"]
        assert key.expires is not None
        assert abs((key.expires - datetime.fromtimestamp(decoded["exp"], tz=timezone.utc).replace(tzinfo=None)).total_seconds()) < 5

        # hashed_key is now the SHA256 of the JTI.
        import hashlib
        expected_hash = hashlib.sha256(decoded["jti"].encode("utf-8")).hexdigest()
        assert key.hashed_key == expected_hash


@pytest.mark.asyncio
async def test_revoke_api_key_blacklists_jti():
    async with SessionLocal() as db:
        u = User(username="revokeuser@example.com", hashed_password="x", is_active=True)
        db.add(u)
        await db.commit()
        await db.refresh(u)

        result = await users_crud.create_key("revoke-me", u, None, db)
        token = result["token"]
        key_id = result["id"]

        await users_crud.blacklist_api_key(key_id, db, requesting_user=u)

        # The APIKEY row is gone.
        res = await db.execute(select(APIKEY).filter(APIKEY.id == key_id))
        assert res.scalars().first() is None

        # The jti is in the blacklist.
        decoded = _pyjwt.decode(token, get_secret_key(), algorithms=["HS256"])
        res2 = await db.execute(select(TokenBlacklist).filter(TokenBlacklist.jti == decoded["jti"]))
        row = res2.scalars().first()
        assert row is not None
        assert row.revoked is True

        # The token itself is rejected.
        exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="x")
        with pytest.raises(HTTPException):
            await verify_token(token, exc)
