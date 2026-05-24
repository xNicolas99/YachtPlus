"""Regression for BUG-016: the unified /search endpoint accepted an
unbounded `q` and never capped its results. A pathological caller could
pass a 1-MB query string (forcing an expensive LIKE scan of the
templates table) and walk away with the entire result set serialized to
JSON. The fix puts a min_length/max_length on `q` and slices both result
arrays to SEARCH_RESULT_LIMIT before returning.
"""
import asyncio
import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.database import Base
from api.routers import search as search_module
from api.routers.search import search, SEARCH_QUERY_MAX_LEN, SEARCH_RESULT_LIMIT, limiter as _search_limiter


@pytest.fixture(autouse=True)
def _disable_search_limiter(monkeypatch):
    monkeypatch.setattr(_search_limiter, "enabled", False)


engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class MockAuth:
    def jwt_required(self, allow_setup_pending=False):
        return True

    def get_jwt_subject(self, allow_setup_pending=False):
        return "anyuser"


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    yield s
    s.close()


def test_search_result_limit_constant_is_sane():
    # If someone bumps the cap into the thousands the fix loses meaning;
    # this lock keeps the value within a defensible range.
    assert 10 <= SEARCH_RESULT_LIMIT <= 500
    assert 16 <= SEARCH_QUERY_MAX_LEN <= 1024


def test_search_caps_template_results(db, monkeypatch):
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
    monkeypatch.setattr(search_module, "match_templates", lambda _db, _q: overflow)

    result = asyncio.get_event_loop().run_until_complete(
        search(request=MagicMock(), q="nginx", db=db, Authorize=MockAuth())
    )
    assert len(result["templates"]) == SEARCH_RESULT_LIMIT


def test_search_caps_dockerhub_results(db, monkeypatch):
    overflow = [{"name": f"img-{i}"} for i in range(SEARCH_RESULT_LIMIT + 25)]

    async def fake_registry(*_a, **_kw):
        return overflow

    monkeypatch.setattr(search_module.registries, "search_registry", fake_registry)
    monkeypatch.setattr(search_module, "match_templates", lambda _db, _q: [])

    result = asyncio.get_event_loop().run_until_complete(
        search(request=MagicMock(), q="nginx", db=db, Authorize=MockAuth())
    )
    assert len(result["dockerhub"]) == SEARCH_RESULT_LIMIT
