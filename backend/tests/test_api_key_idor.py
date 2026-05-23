"""Regression for the IDOR on /api/keys/{key_id} delete (BUG-001).

Before the fix, any authenticated user could pass an arbitrary key_id and
delete someone else's API key. Verify the ownership check.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.database import Base
from api.db.models.users import User, APIKEY
from api.db.crud.users import blacklist_api_key


engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    yield s
    s.close()


def _user(db, username, is_superuser=False):
    u = User(username=username, hashed_password="pw", is_superuser=is_superuser)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _key(db, owner_id, name="k", jti="jti-1"):
    k = APIKEY(key_name=name, jti=jti, hashed_key=f"h-{jti}", user=owner_id)
    db.add(k)
    db.commit()
    db.refresh(k)
    return k


def test_owner_can_delete_own_key(db):
    alice = _user(db, "alice")
    k = _key(db, alice.id, jti="alice-key")

    result = blacklist_api_key(k.id, db, requesting_user=alice)

    assert "success" in result
    assert db.query(APIKEY).filter(APIKEY.id == k.id).first() is None


def test_non_owner_cannot_delete_other_user_key(db):
    alice = _user(db, "alice")
    bob = _user(db, "bob")
    alice_key = _key(db, alice.id, jti="alice-key")

    result = blacklist_api_key(alice_key.id, db, requesting_user=bob)

    # Same "not found" message as for a missing key, so we don't leak
    # whether the id maps to another account.
    assert "error" in result
    # Alice's key is still there.
    assert db.query(APIKEY).filter(APIKEY.id == alice_key.id).first() is not None


def test_superuser_can_delete_any_key(db):
    alice = _user(db, "alice")
    admin = _user(db, "root", is_superuser=True)
    k = _key(db, alice.id, jti="alice-key")

    result = blacklist_api_key(k.id, db, requesting_user=admin)

    assert "success" in result
    assert db.query(APIKEY).filter(APIKEY.id == k.id).first() is None


def test_missing_key_returns_not_found(db):
    alice = _user(db, "alice")
    result = blacklist_api_key(9999, db, requesting_user=alice)
    assert "error" in result


def test_legacy_call_without_requester_still_works(db):
    """blacklist_api_key keeps its optional-requester signature so call
    sites that genuinely don't need the ownership check (admin scripts,
    migrations) still function — only the router enforces it.
    """
    alice = _user(db, "alice")
    k = _key(db, alice.id, jti="legacy-key")

    result = blacklist_api_key(k.id, db)  # no requesting_user

    assert "success" in result
