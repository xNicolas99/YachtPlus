import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.db.database import Base
from api.db.models.users import User
import pyotp
from fastapi import HTTPException

engine = create_engine('sqlite:///:memory:')
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)
db = SessionLocal()

from api.routers.auth_2fa import generate_2fa_get, generate_2fa, enable_2fa, disable_2fa, TwoFactorRequest

class MockAuth:
    def __init__(self, username):
        self.username = username
    def jwt_required(self, allow_setup_pending=False):
        return True
    def get_jwt_subject(self, allow_setup_pending=False):
        return self.username

def test_generate_2fa_get_success():
    u1 = User(username="2fauser", hashed_password="pw", is_superuser=False)
    db.add(u1)
    db.commit()

    auth = MockAuth("2fauser")

    result = generate_2fa_get(db=db, Authorize=auth)

    assert "secret" in result
    assert "qr_code" in result
    assert "provisioning_uri" in result
    assert result["secret"] is not None
    assert result["qr_code"].startswith("data:image/png;base64,")
    assert "2fauser" in result["provisioning_uri"]

def test_generate_2fa_get_user_not_found():
    auth = MockAuth("unknownuser")

    with pytest.raises(HTTPException) as exc:
        generate_2fa_get(db=db, Authorize=auth)

    assert exc.value.status_code == 404
    assert exc.value.detail == "User not found"

def test_enable_2fa_success():
    u1 = User(username="enableuser", hashed_password="pw", is_superuser=False)
    db.add(u1)
    db.commit()

    auth = MockAuth("enableuser")

    # First generate to set secret
    gen_result = generate_2fa_get(db=db, Authorize=auth)
    secret = gen_result["secret"]

    # Now verify with code
    totp = pyotp.TOTP(secret)
    code = totp.now()

    req = TwoFactorRequest(code=code)
    result = enable_2fa(payload=req, db=db, Authorize=auth)

    assert result == {"message": "2FA enabled successfully"}

    # Check DB
    db.refresh(u1)
    assert u1.is_2fa_enabled == True

def test_enable_2fa_invalid_code():
    u1 = User(username="invalidcodeuser", hashed_password="pw", is_superuser=False)
    db.add(u1)
    db.commit()

    auth = MockAuth("invalidcodeuser")

    # First generate to set secret
    generate_2fa_get(db=db, Authorize=auth)

    req = TwoFactorRequest(code="000000")
    with pytest.raises(HTTPException) as exc:
        enable_2fa(payload=req, db=db, Authorize=auth)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid token or secret error"

def test_enable_2fa_not_initiated():
    u1 = User(username="notinitiateduser", hashed_password="pw", is_superuser=False)
    db.add(u1)
    db.commit()

    auth = MockAuth("notinitiateduser")

    # Try enabling without generating first
    req = TwoFactorRequest(code="123456")
    with pytest.raises(HTTPException) as exc:
        enable_2fa(payload=req, db=db, Authorize=auth)

    assert exc.value.status_code == 400
    assert exc.value.detail == "2FA setup not initiated"

def test_disable_2fa_success():
    u1 = User(username="disableuser", hashed_password="pw", is_superuser=False, is_2fa_enabled=True, otp_secret="some_secret")
    db.add(u1)
    db.commit()

    auth = MockAuth("disableuser")

    result = disable_2fa(db=db, Authorize=auth)

    assert result == {"message": "2FA disabled successfully"}

    # Check DB
    db.refresh(u1)
    assert u1.is_2fa_enabled == False
    assert u1.otp_secret is None

def test_generate_2fa_post_success():
    u1 = User(username="2fapostuser", hashed_password="pw", is_superuser=False)
    db.add(u1)
    db.commit()

    auth = MockAuth("2fapostuser")

    result = generate_2fa(db=db, Authorize=auth)

    assert "secret" in result
    assert "qr_code" in result
    assert "provisioning_uri" in result
    assert result["secret"] is not None
    assert result["qr_code"].startswith("data:image/png;base64,")
    assert "2fapostuser" in result["provisioning_uri"]
