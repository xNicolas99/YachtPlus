"""Regression for the IDOR on /api/keys/{key_id} delete (BUG-001).

Before the fix, any authenticated user could pass an arbitrary key_id and
delete someone else's API key. Verify the ownership check.
"""
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlalchemy import select

from api.db.database import Base
from api.db.models.users import User, APIKEY
from api.db.crud.users import blacklist_api_key


engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        yield s


async def _user(db, username, is_superuser=False):
    u = User(username=username, hashed_password="pw", is_superuser=is_superuser)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _key(db, owner_id, name="k", jti="jti-1"):
    k = APIKEY(key_name=name, jti=jti, hashed_key=f"h-{jti}", user=owner_id)
    db.add(k)
    await db.commit()
    await db.refresh(k)
    return k


@pytest.mark.asyncio
async def test_owner_can_delete_own_key(db):
    alice = await _user(db, "alice")
    k = await _key(db, alice.id, jti="alice-key")

    result = await blacklist_api_key(k.id, db, requesting_user=alice)

    assert "message" in result
    res = await db.execute(select(APIKEY).filter(APIKEY.id == k.id))
    assert res.scalars().first() is None


@pytest.mark.asyncio
async def test_non_owner_cannot_delete_other_user_key(db):
    alice = await _user(db, "alice")
    bob = await _user(db, "bob")
    alice_key = await _key(db, alice.id, jti="alice-key")

    with pytest.raises(HTTPException) as exc:
        await blacklist_api_key(alice_key.id, db, requesting_user=bob)

    assert exc.value.status_code == 404
    # Alice's key is still there.
    res = await db.execute(select(APIKEY).filter(APIKEY.id == alice_key.id))
    assert res.scalars().first() is not None


@pytest.mark.asyncio
async def test_superuser_can_delete_any_key(db):
    alice = await _user(db, "alice")
    admin = await _user(db, "root", is_superuser=True)
    k = await _key(db, alice.id, jti="alice-key")

    result = await blacklist_api_key(k.id, db, requesting_user=admin)

    assert "message" in result
    res = await db.execute(select(APIKEY).filter(APIKEY.id == k.id))
    assert res.scalars().first() is None


@pytest.mark.asyncio
async def test_missing_key_returns_not_found(db):
    alice = await _user(db, "alice")
    with pytest.raises(HTTPException) as exc:
        await blacklist_api_key(9999, db, requesting_user=alice)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_legacy_call_without_requester_still_works(db):
    """blacklist_api_key keeps its optional-requester signature so call
    sites that genuinely don't need the ownership check (admin scripts,
    migrations) still function — only the router enforces it.
    """
    alice = await _user(db, "alice")
    k = await _key(db, alice.id, jti="legacy-key")

    result = await blacklist_api_key(k.id, db)  # no requesting_user

    assert "message" in result
