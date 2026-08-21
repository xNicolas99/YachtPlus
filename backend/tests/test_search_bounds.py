"""Regression for BUG-016: the unified /search endpoint accepted an
unbounded `q` and never capped its results. A pathological caller could
pass a 1-MB query string (forcing an expensive LIKE scan of the
templates table) and walk away with the entire result set serialized to
JSON. The fix puts a min_length/max_length on `q` and slices both result
arrays to SEARCH_RESULT_LIMIT before returning.
"""
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from api.db.database import Base
from api.routers import search as search_module
from api.routers.search import search, SEARCH_QUERY_MAX_LEN, SEARCH_RESULT_LIMIT, limiter as _search_limiter


@pytest.fixture(autouse=True)
def _disable_search_limiter(monkeypatch):
    monkeypatch.setattr(_search_limiter, "enabled", False)


_ASYNC_TEST_ENGINE = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    poolclass=StaticPool,
)
_ASYNC_TEST_SESSION = async_sessionmaker(
    bind=_ASYNC_TEST_ENGINE,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class MockAuth:
    async def jwt_required(self, allow_setup_pending=False):
        return True

    async def get_jwt_subject(self, allow_setup_pending=False):
        return "anyuser"


@pytest_asyncio.fixture
async def db():
    async with _ASYNC_TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with _ASYNC_TEST_SESSION() as session:
        yield session


def test_search_result_limit_constant_is_sane():
    # If someone bumps the cap into the thousands the fix loses meaning;
    # this lock keeps the value within a defensible range.
    assert 10 <= SEARCH_RESULT_LIMIT <= 500
    assert 16 <= SEARCH_QUERY_MAX_LEN <= 1024


@pytest.mark.asyncio
async def test_search_caps_template_results(db, monkeypatch):
    class FakeTemplate:
        def __init__(self, i):
            self.id = i
            self.title = f"t{i}"
            self.name = f"n{i}"
            self.description = ""
            self.image = ""
            self.logo = ""
            self.url = ""

    overflow = [FakeTemplate(i) for i in range(SEARCH_RESULT_LIMIT + 50)]

    async def fake_registry(*_a, **_kw):
        return []

    monkeypatch.setattr(search_module.registries, "search_registry", fake_registry)

    async def fake_match(_db, _q):
        return overflow

    monkeypatch.setattr(search_module, "match_templates", fake_match)

    result = await search(request=MagicMock(), q="nginx", db=db, Authorize=MockAuth())
    assert len(result["templates"]) == SEARCH_RESULT_LIMIT


@pytest.mark.asyncio
async def test_search_caps_dockerhub_results(db, monkeypatch):
    overflow = [{"name": f"img-{i}"} for i in range(SEARCH_RESULT_LIMIT + 25)]

    async def fake_registry(*_a, **_kw):
        return overflow

    monkeypatch.setattr(search_module.registries, "search_registry", fake_registry)

    async def fake_match(_db, _q):
        return []

    monkeypatch.setattr(search_module, "match_templates", fake_match)

    result = await search(request=MagicMock(), q="nginx", db=db, Authorize=MockAuth())
    assert len(result["dockerhub"]) == SEARCH_RESULT_LIMIT
