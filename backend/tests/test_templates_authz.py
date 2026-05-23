"""Regression for BUG-002: write endpoints on /api/templates/* were ungated.

add_template, delete, refresh_template now require a superuser caller.
"""
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from api.db.database import Base
from api.db.models.users import User
from api.routers.templates import add_template, delete, refresh_template
from api.db.schemas.templates import TemplateBase


engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    yield s
    s.close()


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


def _user(db, username, is_superuser=False):
    u = User(username=username, hashed_password="pw", is_superuser=is_superuser)
    db.add(u)
    db.commit()
    return u


def test_add_template_rejects_non_superuser(db):
    _user(db, "ops", is_superuser=False)
    payload = TemplateBase(title="t", url="http://example.test/x.json")

    with pytest.raises(HTTPException) as exc:
        add_template(payload, db=db, Authorize=MockAuth("ops"))

    assert exc.value.status_code == 403


def test_add_template_allows_superuser(db):
    _user(db, "root", is_superuser=True)
    payload = TemplateBase(title="t", url="http://example.test/x.json")

    with patch("api.routers.templates.crud.get_template", return_value=None), \
         patch("api.routers.templates.crud.add_template", return_value=MagicMock(title="t")):
        result = add_template(payload, db=db, Authorize=MockAuth("root"))

    assert result.title == "t"


def test_delete_template_rejects_non_superuser(db):
    _user(db, "ops", is_superuser=False)

    with pytest.raises(HTTPException) as exc:
        delete(id=1, db=db, Authorize=MockAuth("ops"))

    assert exc.value.status_code == 403


def test_delete_template_allows_superuser(db):
    _user(db, "root", is_superuser=True)

    with patch("api.routers.templates.crud.delete_template", return_value=MagicMock()):
        # Should not raise.
        delete(id=1, db=db, Authorize=MockAuth("root"))


def test_refresh_template_rejects_non_superuser(db):
    _user(db, "ops", is_superuser=False)

    with pytest.raises(HTTPException) as exc:
        refresh_template(id=1, db=db, Authorize=MockAuth("ops"))

    assert exc.value.status_code == 403


def test_refresh_template_allows_superuser(db):
    _user(db, "root", is_superuser=True)

    with patch("api.routers.templates.crud.refresh_template", return_value=MagicMock()):
        refresh_template(id=1, db=db, Authorize=MockAuth("root"))


def test_unknown_user_token_is_rejected(db):
    """JWT subject points at a username that doesn't exist in the DB."""
    with pytest.raises(HTTPException) as exc:
        delete(id=1, db=db, Authorize=MockAuth("ghost"))
    assert exc.value.status_code == 401
