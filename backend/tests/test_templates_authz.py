"""Regression for BUG-002: write endpoints on /api/templates/* were ungated.

add_template, delete, refresh_template now require a superuser caller.
"""
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from api.db.database import Base
from api.db.models.users import User
from api.routers.templates import add_template, delete, refresh_template
from api.db.schemas.templates import TemplateBase
from tests.conftest import _ASYNC_TEST_ENGINE, _ASYNC_TEST_SESSION


@pytest_asyncio.fixture
async def db():
    async with _ASYNC_TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with _ASYNC_TEST_SESSION() as session:
        yield session


class MockAuth:
    def __init__(self, username):
        self.username = username

    async def jwt_required(self, allow_setup_pending=False):
        return True

    async def get_jwt_subject(self, allow_setup_pending=False):
        return self.username


@pytest.fixture(autouse=True)
def enable_auth(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


async def _user(db, username, is_superuser=False):
    u = User(username=username, hashed_password="pw", is_superuser=is_superuser)
    db.add(u)
    await db.commit()
    return u


@pytest.mark.asyncio
async def test_add_template_rejects_non_superuser(db):
    await _user(db, "ops", is_superuser=False)
    payload = TemplateBase(title="t", url="http://example.test/x.json")

    with pytest.raises(HTTPException) as exc:
        await add_template(payload, db=db, Authorize=MockAuth("ops"))

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_add_template_allows_superuser(db):
    await _user(db, "root", is_superuser=True)
    payload = TemplateBase(title="t", url="http://example.test/x.json")

    with patch("api.routers.templates.crud.get_template", return_value=None), \
         patch("api.routers.templates.crud.add_template", return_value=MagicMock(title="t")):
        result = await add_template(payload, db=db, Authorize=MockAuth("root"))

    assert result.title == "t"


@pytest.mark.asyncio
async def test_delete_template_rejects_non_superuser(db):
    await _user(db, "ops", is_superuser=False)

    with pytest.raises(HTTPException) as exc:
        await delete(id=1, db=db, Authorize=MockAuth("ops"))

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_template_allows_superuser(db):
    await _user(db, "root", is_superuser=True)

    with patch("api.routers.templates.crud.delete_template", return_value=MagicMock()):
        # Should not raise.
        await delete(id=1, db=db, Authorize=MockAuth("root"))


@pytest.mark.asyncio
async def test_refresh_template_rejects_non_superuser(db):
    await _user(db, "ops", is_superuser=False)

    with pytest.raises(HTTPException) as exc:
        await refresh_template(id=1, db=db, Authorize=MockAuth("ops"))

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_refresh_template_allows_superuser(db):
    await _user(db, "root", is_superuser=True)

    with patch("api.routers.templates.crud.refresh_template", return_value=MagicMock()):
        await refresh_template(id=1, db=db, Authorize=MockAuth("root"))


@pytest.mark.asyncio
async def test_unknown_user_token_is_rejected(db):
    """JWT subject points at a username that doesn't exist in the DB."""
    with pytest.raises(HTTPException) as exc:
        await delete(id=1, db=db, Authorize=MockAuth("ghost"))
    assert exc.value.status_code == 401
