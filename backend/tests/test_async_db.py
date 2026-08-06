"""Async-migration regression tests.

Pins the async DB layer that replaced the previous sync/async mix:
  - the `get_db` dependency yields an AsyncSession and closes it,
  - CRUD operations run through `await db.execute(select(...))`,
  - failed commits roll back without leaving partial state,
  - SQLite (aiosqlite) works end-to-end for an async engine.
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlalchemy import select, func

from api.db.database import Base
from api.db.models.users import User
from api.db.crud.users import create_user, get_user_by_name, _normalize_username
from api.db.schemas.users import UserCreate
from api.utils.auth import get_db
from fastapi import HTTPException


engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        yield session


@pytest.mark.asyncio
async def test_get_db_dependency_yields_async_session():
    """The async get_db dependency yields an AsyncSession and closes it."""
    gen = get_db()
    session = await anext(gen)
    from sqlalchemy.ext.asyncio import AsyncSession
    assert isinstance(session, AsyncSession)
    with pytest.raises(StopAsyncIteration):
        await anext(gen)


@pytest.mark.asyncio
async def test_async_crud_select_and_create(db):
    """create_user + get_user_by_name run through the async session."""
    user = await create_user(db, UserCreate(username="alice", password="pw"))
    assert user.username == "alice"

    found = await get_user_by_name(db, "ALICE")  # casefolded lookup
    assert found is not None
    assert found.username == "alice"


@pytest.mark.asyncio
async def test_commit_persists_and_refresh_works(db):
    """A committed async transaction is visible to a later select."""
    u = User(username="bob", hashed_password="pw")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    assert u.id is not None

    result = await db.execute(select(User).filter(User.username == "bob"))
    assert result.scalars().first() is not None


@pytest.mark.asyncio
async def test_duplicate_username_rolls_back(db):
    """A failing commit rolls back and leaves the DB clean."""
    await create_user(db, UserCreate(username="carol", password="pw"))

    # Second create with the same canonical username must raise + rollback.
    with pytest.raises(HTTPException):
        await create_user(db, UserCreate(username="CAROL", password="pw"))

    result = await db.execute(
        select(func.count()).select_from(User)
    )
    # Only the original carol row exists — no partial duplicate.
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_rollback_after_forced_db_error(db):
    """Rollback leaves no partial write behind after an error."""
    # Force a unique-constraint violation directly on the session.
    u1 = User(username="dup", hashed_password="pw")
    db.add(u1)
    await db.commit()

    u2 = User(id=1, username="dup", hashed_password="pw")  # duplicate pk + username
    db.add(u2)
    try:
        await db.commit()
        pytest.fail("expected commit to fail on duplicate PK")
    except Exception:
        await db.rollback()

    # After rollback the original row is still there, unmodified.
    result = await db.execute(select(User).filter(User.username == "dup"))
    row = result.scalars().first()
    assert row is not None
    assert row.hashed_password == "pw"
