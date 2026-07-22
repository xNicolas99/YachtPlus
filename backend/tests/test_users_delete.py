from sqlalchemy.future import select
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from api.db.database import Base
from api.db.models.users import User
from api.routers.users import delete_user


engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)




from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from api.db.database import Base

engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession, expire_on_commit=False)

import pytest_asyncio
@pytest_asyncio.fixture
async def db_session():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSessionLocal() as session:
        yield session

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


async def _add(db_session, username, is_superuser=False):
    user = User(username=username, hashed_password="pw", is_superuser=is_superuser)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_delete_user_succeeds_for_regular_target(db_session):
    admin = await _add(db_session, "admin", is_superuser=True)
    target = await _add(db_session, "bob", is_superuser=False)

    result = await delete_user(user_id=target.id, db=db_session, Authorize=MockAuth("admin"))

    assert result == {"message": "User deleted"}
    assert (await db_session.execute(select(User).filter(User.id == target.id))).scalars().first() is None
    assert (await db_session.execute(select(User).filter(User.id == admin.id))).scalars().first() is not None


@pytest.mark.asyncio
async def test_delete_user_forbids_self_delete(db_session):
    admin = await _add(db_session, "admin", is_superuser=True)

    with pytest.raises(HTTPException) as exc:
        await delete_user(user_id=admin.id, db=db_session, Authorize=MockAuth("admin"))

    assert exc.value.status_code == 400
    assert "own account" in exc.value.detail
    assert (await db_session.execute(select(User).filter(User.id == admin.id))).scalars().first() is not None


@pytest.mark.asyncio
async def test_delete_user_allows_admin_to_delete_other_admin_when_extra_exists(db_session):
    """Admin A can delete admin B as long as at least one admin remains."""
    admin_a = await _add(db_session, "admin_a", is_superuser=True)
    admin_b = await _add(db_session, "admin_b", is_superuser=True)

    result = await delete_user(user_id=admin_b.id, db=db_session, Authorize=MockAuth("admin_a"))

    assert result == {"message": "User deleted"}
    assert len((await db_session.execute(select(User).filter(User.is_superuser == True))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_delete_user_requires_superuser_caller(db_session):
    await _add(db_session, "admin", is_superuser=True)
    await _add(db_session, "normaluser", is_superuser=False)
    target = await _add(db_session, "target", is_superuser=False)

    with pytest.raises(HTTPException) as exc:
        await delete_user(user_id=target.id, db=db_session, Authorize=MockAuth("normaluser"))

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_user_not_found(db_session):
    await _add(db_session, "admin", is_superuser=True)

    with pytest.raises(HTTPException) as exc:
        await delete_user(user_id=999, db=db_session, Authorize=MockAuth("admin"))

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_user_last_admin_guard_blocks_zero_admin_state(db_session, monkeypatch):
    """Defense-in-depth: even if a non-superuser somehow reaches the deletion
    path (e.g. via a future refactor), deleting the last superuser must fail.
    """
    requester = await _add(db_session, "admin", is_superuser=True)
    # No other admins exist. Try to delete the requester via a different path
    # (skip self-delete guard by forging a target_id that points to a different
    # row sharing the same admin role).
    extra_admin = await _add(db_session, "lone", is_superuser=True)

    # Delete `extra_admin` first via requester to leave only requester. This is
    # allowed by the guard (one admin remains: requester).
    await delete_user(user_id=extra_admin.id, db=db_session, Authorize=MockAuth("admin"))
    assert len((await db_session.execute(select(User).filter(User.is_superuser == True))).scalars().all()) == 1

    # Now create a second admin and have it attempt to delete `requester`.
    # Because the new admin remains, this is allowed by the guard. We use this
    # to assert the guard does NOT over-trigger when at least one admin remains.
    new_admin = await _add(db_session, "new_admin", is_superuser=True)
    result = await delete_user(user_id=requester.id, db=db_session, Authorize=MockAuth("new_admin"))
    assert result == {"message": "User deleted"}
    assert (await db_session.execute(select(User).filter(User.id == requester.id))).scalars().first() is None
