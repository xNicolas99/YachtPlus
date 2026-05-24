"""Regression for BUG-011: disable_2fa used to drop the second factor
purely on a valid session cookie. A hijacked session (XSS, stolen cookie,
sidejacked API key) was enough to downgrade a 2FA-protected account
back to single-factor auth. The fix requires password reconfirmation
plus a fresh TOTP code when 2FA is currently enabled.
"""
import pyotp
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.database import Base
from api.db.models.users import User
from api.db.crud.users import get_password_hash
from api.utils.crypto import encrypt
from api.routers.auth_2fa import disable_2fa, Disable2FARequest


engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class MockAuth:
    def __init__(self, username):
        self.username = username

    def jwt_required(self, allow_setup_pending=False):
        return True

    def get_jwt_subject(self, allow_setup_pending=False):
        return self.username


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _force_auth_on(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


def _seed(db, password, *, twofa=True):
    secret = pyotp.random_base32()
    db.add(User(
        username="alice",
        hashed_password=get_password_hash(password),
        is_2fa_enabled=twofa,
        otp_secret=encrypt(secret) if twofa else None,
    ))
    db.commit()
    return secret


def test_disable_2fa_rejects_wrong_password(db):
    _seed(db, "rightpass")
    payload = Disable2FARequest(password="wrongpass", code="000000")
    with pytest.raises(HTTPException) as exc:
        disable_2fa(payload=payload, db=db, Authorize=MockAuth("alice"))
    assert exc.value.status_code == 400
    assert "Password" in exc.value.detail or "password" in exc.value.detail
    # State must remain — the whole point of the fix.
    user = db.query(User).filter(User.username == "alice").first()
    assert user.is_2fa_enabled is True
    assert user.otp_secret is not None


def test_disable_2fa_requires_totp_when_enabled(db):
    _seed(db, "rightpass")
    payload = Disable2FARequest(password="rightpass")  # no code
    with pytest.raises(HTTPException) as exc:
        disable_2fa(payload=payload, db=db, Authorize=MockAuth("alice"))
    assert exc.value.status_code == 400
    user = db.query(User).filter(User.username == "alice").first()
    assert user.is_2fa_enabled is True


def test_disable_2fa_rejects_bad_totp(db):
    _seed(db, "rightpass")
    payload = Disable2FARequest(password="rightpass", code="000000")
    with pytest.raises(HTTPException) as exc:
        disable_2fa(payload=payload, db=db, Authorize=MockAuth("alice"))
    assert exc.value.status_code == 400
    user = db.query(User).filter(User.username == "alice").first()
    assert user.is_2fa_enabled is True


def test_disable_2fa_accepts_password_plus_fresh_totp(db):
    secret = _seed(db, "rightpass")
    code = pyotp.TOTP(secret).now()
    payload = Disable2FARequest(password="rightpass", code=code)
    res = disable_2fa(payload=payload, db=db, Authorize=MockAuth("alice"))
    assert res == {"message": "2FA disabled successfully"}
    user = db.query(User).filter(User.username == "alice").first()
    assert user.is_2fa_enabled is False
    assert user.otp_secret is None


def test_disable_2fa_idempotent_when_not_enabled(db):
    """If 2FA was never enabled, we only require password — no TOTP."""
    _seed(db, "rightpass", twofa=False)
    payload = Disable2FARequest(password="rightpass")
    res = disable_2fa(payload=payload, db=db, Authorize=MockAuth("alice"))
    assert res == {"message": "2FA disabled successfully"}
