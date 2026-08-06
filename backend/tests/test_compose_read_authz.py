"""Regression for BUG-007: the compose read endpoints (GET /api/compose
and GET /api/compose/{project_name}) were gated by `auth_check` only —
so any authenticated user, including a no-perm read-only account, could:

  - enumerate every compose project on the host (list endpoint), and
  - dump the raw YAML of any project (detail endpoint), which routinely
    contains secrets stored as `environment` values.

The fix gates the listing behind perm_start and the detail behind
superuser (matching the support-bundle endpoint).
"""
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

from api.db.database import Base
from api.db.models.users import User
from api.routers.compose import get_projects, get_project


engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


class MockAuth:
    def __init__(self, username):
        self.username = username

    async def jwt_required(self, allow_setup_pending=False):
        return True

    async def get_jwt_subject(self, allow_setup_pending=False):
        return self.username


@pytest.fixture(autouse=True)
def _force_auth_on(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        s.add(User(username="bob", hashed_password="pw", is_superuser=False))
        s.add(User(username="ops", hashed_password="pw", is_superuser=False, perm_start=True))
        s.add(User(username="root", hashed_password="pw", is_superuser=True))
        await s.commit()
        yield s


@pytest.mark.asyncio
async def test_list_requires_perm_start(db):
    """A bare authed user (no perm_start) can no longer enumerate projects."""
    with pytest.raises(HTTPException) as exc:
        await get_projects(Authorize=MockAuth("bob"), db=db)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_allowed_for_perm_start(db):
    with patch("api.routers.compose.get_compose_projects", return_value=[]) as inner:
        result = await get_projects(Authorize=MockAuth("ops"), db=db)
    inner.assert_awaited_once()
    assert result == []


@pytest.mark.asyncio
async def test_detail_requires_superuser_not_perm_start(db):
    """perm_start is enough to *operate* a stack but NOT enough to read
    its raw YAML — that would leak secrets stored as environment values."""
    with pytest.raises(HTTPException) as exc:
        await get_project("anything", Authorize=MockAuth("ops"), db=db)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_detail_allowed_for_superuser(db):
    with patch("api.routers.compose.get_compose", return_value={"name": "p"}) as inner:
        result = await get_project("p", Authorize=MockAuth("root"), db=db)
    inner.assert_awaited_once_with("p")
    assert result == {"name": "p"}
