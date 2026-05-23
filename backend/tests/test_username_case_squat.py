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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from api.db.database import Base
from api.db.models.users import User
from api.db.crud.users import (
    create_user,
    update_user,
    update_user_by_id,
    get_user_by_name,
    _normalize_username,
    _username_is_taken,
)
from api.db.schemas.users import UserCreate, UserUpdate


engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    yield s
    s.close()


def _add_raw(db, username, **kw):
    """Insert a user *without* going through create_user — used only to
    simulate the pre-fix state where a mixed-case admin name might have
    been persisted by old code paths."""
    defaults = dict(hashed_password="pw", is_active=True, is_superuser=False)
    defaults.update(kw)
    u = User(username=username, **defaults)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ---- normalization helpers ------------------------------------------------

def test_normalize_username_lowercases_and_strips():
    assert _normalize_username("Admin") == "admin"
    assert _normalize_username("  ADMIN  ") == "admin"
    assert _normalize_username("MiXeD") == "mixed"


def test_username_is_taken_is_case_insensitive(db):
    # Legacy mixed-case row must still be detected by the helper —
    # otherwise the case-squat attack remains possible against installs
    # that already have an "Admin" in the DB.
    _add_raw(db, "Admin")
    assert _username_is_taken(db, "admin") is True
    assert _username_is_taken(db, "ADMIN") is True

    _add_raw(db, "alice")
    assert _username_is_taken(db, "ALICE") is True
    assert _username_is_taken(db, "alice") is True


def test_username_is_taken_respects_excluding_id(db):
    u = _add_raw(db, "bob")
    assert _username_is_taken(db, "bob", excluding_id=u.id) is False
    assert _username_is_taken(db, "bob") is True


# ---- create_user normalizes ----------------------------------------------

def test_create_user_normalizes_username(db):
    u = create_user(db, UserCreate(username="Admin", password="pw"))
    assert u.username == "admin"


def test_create_user_rejects_case_collision(db):
    create_user(db, UserCreate(username="admin", password="pw"))
    with pytest.raises(HTTPException) as exc:
        create_user(db, UserCreate(username="Admin", password="pw"))
    assert exc.value.status_code == 409


def test_create_user_strips_whitespace(db):
    u = create_user(db, UserCreate(username="  alice  ", password="pw"))
    assert u.username == "alice"


# ---- the actual attack: self-rename to squat an admin name ---------------

def test_self_rename_cannot_squat_existing_admin_case_variant(db):
    """Attack reproduction. Pre-fix this used to succeed."""
    # Real admin, persisted with mixed case (simulating old setup-wizard data).
    _add_raw(db, "Admin", is_superuser=True)
    # Attacker exists as a regular user.
    evil = _add_raw(db, "evil", is_superuser=False)

    with pytest.raises(HTTPException) as exc:
        update_user(
            db,
            UserUpdate(username="admin"),
            current_user="evil",
        )
    assert exc.value.status_code == 409

    # Attacker row is unchanged.
    db.refresh(evil)
    assert evil.username == "evil"


def test_self_rename_to_unique_name_still_works(db):
    _add_raw(db, "alice")
    updated = update_user(
        db, UserUpdate(username="alice_new"), current_user="alice",
    )
    assert updated is not None
    assert updated.username == "alice_new"


def test_login_lookup_matches_canonical_row_only(db):
    """After the fix, the casefolded-login lookup can't be tricked into
    picking a freshly-squatted attacker row over the real admin."""
    _add_raw(db, "admin", is_superuser=True)
    # An attacker tries to rename via create_user — also blocked.
    with pytest.raises(HTTPException):
        create_user(db, UserCreate(username="ADMIN", password="pw"))

    # Lookup still finds the real admin.
    real = get_user_by_name(db, "admin")
    assert real is not None
    assert real.is_superuser is True


# ---- admin-side rename via update_user_by_id -----------------------------

def test_update_by_id_rejects_case_collision(db):
    _add_raw(db, "admin", is_superuser=True)
    target = _add_raw(db, "bob")
    with pytest.raises(HTTPException) as exc:
        update_user_by_id(db, target.id, UserUpdate(username="ADMIN"))
    assert exc.value.status_code == 409


def test_update_by_id_normalizes_when_unique(db):
    target = _add_raw(db, "carol")
    updated = update_user_by_id(db, target.id, UserUpdate(username="CarolNew"))
    assert updated.username == "carolnew"


def test_update_by_id_no_op_username_does_not_collide_with_self(db):
    """Admin re-saving a user without changing the username must not
    trigger a self-collision."""
    target = _add_raw(db, "dave")
    # Same casing (after normalize) should not raise.
    updated = update_user_by_id(db, target.id, UserUpdate(username="Dave"))
    assert updated.username == "dave"
