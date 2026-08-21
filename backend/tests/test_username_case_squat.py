"""Regression for the username case-squat / admin-lockout attack.

Before the fix:
- create_user stored the username as-is (mixed case possible).
- update_user (self-update) casefolded the new value but did NOT check
  whether another row already owned the canonical form.

That asymmetry let a low-privilege user rename themselves to the
casefolded variant of an existing admin, so the next casefolded login
lookup matched the attacker's row and the real admin was effectively
locked out.

The fix casefolds usernames at every write site and rejects collisions
case-insensitively.
"""
import pytest
from fastapi import HTTPException

from api.db.models.users import User
from api.db.crud.users import (
    create_user,
    update_user,
    update_user_by_id,
    get_user_by_name,
    normalize_username,
    _username_is_taken,
)
from api.db.schemas.users import UserCreate, UserUpdate

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from api.db.database import Base
import pytest_asyncio

engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
TestingSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autocommit=False, autoflush=False)


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSessionLocal() as session:
        yield session


async def _add_raw(db, username, **kw):
    """Insert a user *without* going through create_user — used only to
    simulate the pre-fix state where a mixed-case admin name might have
    been persisted by old code paths."""
    defaults = dict(hashed_password="pw", is_active=True, is_superuser=False)
    defaults.update(kw)
    u = User(username=username, **defaults)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


# ---- normalization helpers ------------------------------------------------

def testnormalize_username_lowercases_and_strips():
    assert normalize_username("Admin") == "admin"
    assert normalize_username("  ADMIN  ") == "admin"
    assert normalize_username("MiXeD") == "mixed"


@pytest.mark.asyncio
async def test_username_is_taken_is_case_insensitive(db):
    # Legacy mixed-case row must still be detected by the helper —
    # otherwise the case-squat attack remains possible against installs
    # that already have an "Admin" in the DB.
    await _add_raw(db, "Admin")
    assert await _username_is_taken(db, "admin") is True
    assert await _username_is_taken(db, "ADMIN") is True

    await _add_raw(db, "alice")
    assert await _username_is_taken(db, "ALICE") is True
    assert await _username_is_taken(db, "alice") is True


@pytest.mark.asyncio
async def test_username_is_taken_respects_excluding_id(db):
    u = await _add_raw(db, "bob")
    assert await _username_is_taken(db, "bob", excluding_id=u.id) is False
    assert await _username_is_taken(db, "bob") is True


# ---- create_user normalizes ----------------------------------------------

@pytest.mark.asyncio
async def test_create_user_normalizes_username(db):
    u = await create_user(db, UserCreate(username="Admin", password="pw"))
    assert u.username == "admin"


@pytest.mark.asyncio
async def test_create_user_rejects_case_collision(db):
    await create_user(db, UserCreate(username="admin", password="pw"))
    with pytest.raises(HTTPException) as exc:
        await create_user(db, UserCreate(username="Admin", password="pw"))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_create_user_strips_whitespace(db):
    u = await create_user(db, UserCreate(username="  alice  ", password="pw"))
    assert u.username == "alice"


# ---- the actual attack: self-rename to squat an admin name ---------------

@pytest.mark.asyncio
async def test_self_rename_cannot_squat_existing_admin_case_variant(db):
    """Attack reproduction. Pre-fix this used to succeed."""
    # Real admin, persisted with mixed case (simulating old setup-wizard data).
    await _add_raw(db, "Admin", is_superuser=True)
    # Attacker exists as a regular user.
    evil = await _add_raw(db, "evil", is_superuser=False)

    with pytest.raises(HTTPException) as exc:
        await update_user(
            db,
            UserUpdate(username="admin"),
            current_user="evil",
        )
    assert exc.value.status_code == 409

    # Attacker row is unchanged.
    await db.refresh(evil)
    assert evil.username == "evil"


@pytest.mark.asyncio
async def test_self_rename_to_unique_name_still_works(db):
    await _add_raw(db, "alice")
    updated = await update_user(
        db, UserUpdate(username="alice_new"), current_user="alice",
    )
    assert updated is not None
    assert updated.username == "alice_new"


@pytest.mark.asyncio
async def test_login_lookup_matches_canonical_row_only(db):
    """After the fix, the casefolded-login lookup can't be tricked into
    picking a freshly-squatted attacker row over the real admin."""
    await _add_raw(db, "admin", is_superuser=True)
    # An attacker tries to rename via create_user — also blocked.
    with pytest.raises(HTTPException):
        await create_user(db, UserCreate(username="ADMIN", password="pw"))

    # Lookup still finds the real admin.
    real = await get_user_by_name(db, "admin")
    assert real is not None
    assert real.is_superuser is True


# ---- admin-side rename via update_user_by_id -----------------------------

@pytest.mark.asyncio
async def test_update_by_id_rejects_case_collision(db):
    await _add_raw(db, "admin", is_superuser=True)
    target = await _add_raw(db, "bob")
    with pytest.raises(HTTPException) as exc:
        await update_user_by_id(db, target.id, UserUpdate(username="ADMIN"))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_by_id_normalizes_when_unique(db):
    target = await _add_raw(db, "carol")
    updated = await update_user_by_id(db, target.id, UserUpdate(username="CarolNew"))
    assert updated.username == "carolnew"


@pytest.mark.asyncio
async def test_update_by_id_no_op_username_does_not_collide_with_self(db):
    """Admin re-saving a user without changing the username must not
    trigger a self-collision."""
    target = await _add_raw(db, "dave")
    # Same casing (after normalize) should not raise.
    updated = await update_user_by_id(db, target.id, UserUpdate(username="Dave"))
    assert updated.username == "dave"
