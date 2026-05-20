import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.db.database import Base
from api.db.models.users import User
from api.routers.auth_2fa import enable_2fa, TwoFactorRequest, disable_2fa
from fastapi import HTTPException
from api.utils.crypto import encrypt
import pyotp
from unittest.mock import patch

engine = create_engine('sqlite:///:memory:')
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)
db = SessionLocal()


class MockAuth:
    def __init__(self, username):
        self.username = username

    def jwt_required(self, allow_setup_pending=False):
        return True

    def get_jwt_subject(self, allow_setup_pending=False):
        return self.username


def test_enable_2fa_success():
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    code = totp.now()

    u1 = User(
        username="admin_2fa", hashed_password="pw", is_superuser=True,
        otp_secret=encrypt(secret)
    )
    db.add(u1)
    db.commit()

    res = enable_2fa(
        payload=TwoFactorRequest(code=code), db=db,
        Authorize=MockAuth("admin_2fa")
    )
    assert res == {"message": "2FA enabled successfully"}

    user = db.query(User).filter(User.username == "admin_2fa").first()
    assert user.is_2fa_enabled is True


def test_enable_2fa_invalid_code():
    secret = pyotp.random_base32()

    u1 = User(
        username="admin_2fa_invalid", hashed_password="pw", is_superuser=True,
        otp_secret=encrypt(secret)
    )
    db.add(u1)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        enable_2fa(
            payload=TwoFactorRequest(code="000000"), db=db,
            Authorize=MockAuth("admin_2fa_invalid")
        )

    assert exc.value.status_code == 400
    assert "Invalid token or secret error" in exc.value.detail


def test_enable_2fa_no_setup_initiated():
    u1 = User(
        username="admin_2fa_no_setup", hashed_password="pw", is_superuser=True,
        otp_secret=None
    )
    db.add(u1)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        enable_2fa(
            payload=TwoFactorRequest(code="123456"), db=db,
            Authorize=MockAuth("admin_2fa_no_setup")
        )

    assert exc.value.status_code == 400
    assert "2FA setup not initiated" in exc.value.detail


def test_disable_2fa_success():
    secret = pyotp.random_base32()
    u1 = User(
        username="admin_disable_2fa", hashed_password="pw", is_superuser=True,
        otp_secret=encrypt(secret), is_2fa_enabled=True
    )
    db.add(u1)
    db.commit()

    res = disable_2fa(db=db, Authorize=MockAuth("admin_disable_2fa"))
    assert res == {"message": "2FA disabled successfully"}

    user = db.query(User).filter(User.username == "admin_disable_2fa").first()
    assert user.is_2fa_enabled is False
    assert user.otp_secret is None


def test_generate_2fa_success():
    from api.routers.auth_2fa import generate_2fa_logic
    u1 = User(
        username="admin_generate_2fa", hashed_password="pw", is_superuser=True
    )
    db.add(u1)
    db.commit()

    res = generate_2fa_logic(db=db, Authorize=MockAuth("admin_generate_2fa"))
    assert "secret" in res
    assert "qr_code" in res
    assert "provisioning_uri" in res

    user = db.query(User).filter(User.username == "admin_generate_2fa").first()
    assert user.otp_secret is not None


def test_generate_2fa_user_not_found():
    from api.routers.auth_2fa import generate_2fa_logic

    with pytest.raises(HTTPException) as exc:
        generate_2fa_logic(
            db=db, Authorize=MockAuth("admin_generate_2fa_not_found")
        )

    assert exc.value.status_code == 404
    assert "User not found" in exc.value.detail


def test_generate_2fa_get_route():
    from api.routers.auth_2fa import generate_2fa_get
    u1 = User(
        username="admin_generate_get", hashed_password="pw", is_superuser=True
    )
    db.add(u1)
    db.commit()

    res = generate_2fa_get(db=db, Authorize=MockAuth("admin_generate_get"))
    assert "secret" in res
    assert "qr_code" in res


def test_generate_2fa_post_route():
    from api.routers.auth_2fa import generate_2fa
    u1 = User(
        username="admin_generate_post", hashed_password="pw", is_superuser=True
    )
    db.add(u1)
    db.commit()

    res = generate_2fa(db=db, Authorize=MockAuth("admin_generate_post"))
    assert "secret" in res
    assert "qr_code" in res


def test_get_db_yields_session():
    from api.routers.auth_2fa import get_db
    with patch("api.routers.auth_2fa.SessionLocal") as mock_session_local:
        mock_db = mock_session_local.return_value
        db_generator = get_db()
        db_instance = next(db_generator)
        assert db_instance is mock_db

        try:
            next(db_generator)
        except StopIteration:
            pass

        mock_db.close.assert_called_once()
