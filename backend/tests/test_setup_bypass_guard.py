"""Regression for BUG-001: POST /api/setup/bypass would brick a fresh
deployment. Any unauthenticated caller could flip SetupStatus.is_bypassed
to True on the FIRST request to a fresh instance, after which the setup
middleware stopped short-circuiting /api/* to 428 and every data router
fell through to auth_check — but no user existed, so nobody could ever
log in. The endpoint is now gated behind DISABLE_AUTH=True (dev only).
"""
import pytest
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.database import Base
from api.routers.setup.setup import bypass_setup, is_setup_completed
from api.db.models.setup import SetupStatus


engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    yield s
    s.close()


def test_bypass_rejected_in_production_mode(db, monkeypatch):
    """The brick-DoS path. DISABLE_AUTH is the default False, so a hostile
    caller on a fresh install must get a 404 here."""
    with patch("api.settings.Settings") as fake_settings_cls:
        fake_settings_cls.return_value.DISABLE_AUTH = False
        with pytest.raises(HTTPException) as exc:
            bypass_setup(db=db)
    assert exc.value.status_code == 404
    # Nothing should have been written to SetupStatus.
    assert db.query(SetupStatus).count() == 0
    # is_setup_completed must still be False — the system is still
    # waiting for legit registration.
    assert is_setup_completed(db) is False


def test_bypass_allowed_in_dev_mode(db):
    """In dev mode (DISABLE_AUTH=True) the bypass is intentional — it lets
    a developer skip the wizard on a throwaway DB."""
    with patch("api.settings.Settings") as fake_settings_cls:
        fake_settings_cls.return_value.DISABLE_AUTH = True
        result = bypass_setup(db=db)
    assert "bypassed" in result["message"].lower()
    status = db.query(SetupStatus).first()
    assert status is not None
    assert status.is_bypassed is True


def test_bypass_still_refuses_after_user_exists(db):
    """Even in dev mode, refuse to bypass once a real user has been
    registered — that user would otherwise be silently kept active."""
    from api.db.models.users import User
    db.add(User(username="alice", hashed_password="pw"))
    db.commit()

    with patch("api.settings.Settings") as fake_settings_cls:
        fake_settings_cls.return_value.DISABLE_AUTH = True
        with pytest.raises(HTTPException) as exc:
            bypass_setup(db=db)
    assert exc.value.status_code == 400


def test_bypass_returns_idempotent_message_when_already_completed(db):
    """Calling bypass a second time after legit completion should not
    rewrite the SetupStatus row — just return the no-op message."""
    db.add(SetupStatus(is_complete=True))
    db.commit()

    with patch("api.settings.Settings") as fake_settings_cls:
        fake_settings_cls.return_value.DISABLE_AUTH = True
        result = bypass_setup(db=db)
    assert "already" in result["message"].lower()
    status = db.query(SetupStatus).first()
    # is_complete stays True, is_bypassed not flipped.
    assert status.is_complete is True
    assert status.is_bypassed is not True  # accept False or None
