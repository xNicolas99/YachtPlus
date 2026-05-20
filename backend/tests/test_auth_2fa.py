import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.db.database import Base
from api.db.models.users import User
from fastapi import HTTPException
from api.routers.auth_2fa import disable_2fa

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


def test_disable_2fa_success(monkeypatch):
    monkeypatch.setattr("api.routers.auth_2fa.auth_check", lambda x: None)

    u = User(
        username="testuser",
        hashed_password="pw",
        is_2fa_enabled=True,
        otp_secret="secret"
    )
    db.add(u)
    db.commit()

    res = disable_2fa(db=db, Authorize=MockAuth("testuser"))

    assert res == {"message": "2FA disabled successfully"}

    db_user = db.query(User).filter(User.username == "testuser").first()
    assert db_user.is_2fa_enabled is False
    assert db_user.otp_secret is None


def test_disable_2fa_user_not_found(monkeypatch):
    monkeypatch.setattr("api.routers.auth_2fa.auth_check", lambda x: None)

    with pytest.raises(HTTPException) as exc:
        disable_2fa(db=db, Authorize=MockAuth("nonexistent"))

    assert exc.value.status_code == 404
    assert exc.value.detail == "User not found"
