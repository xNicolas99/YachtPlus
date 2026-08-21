"""Pytest configuration loaded before any test module imports.

Sets environment variables that must be in place before `api.settings`
is imported, because Settings class attributes are evaluated at class
definition time.

Also exposes shared async database fixtures for the SQLAlchemy-async test
setup. After the async migration, the production code (CRUD + routers) is
async and expects an AsyncSession, so tests must use the async engine and
async fixtures. Tests that still spin up their own in-memory engine can
either reuse these fixtures or replicate them (the canonical pattern is
in tests/test_users_delete.py).
"""
import os
import tempfile
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

# Disable slowapi rate-limit decorators before any router module is imported.
# Unit tests call handlers directly without a Request object; without this
# the @limiter.limit wrapper raises at runtime. Integration tests that use
# TestClient still see the real middleware stack.
from slowapi import Limiter
_original_limiter_limit = Limiter.limit

def _noop_limit(self, *args, **kwargs):
    return lambda f: f

Limiter.limit = _noop_limit

# Starlette's TestClient sends Host: testserver by default. Add it to the
# allowed-host list so TrustedHostMiddleware doesn't 400 every request.
os.environ.setdefault(
    "YACHT_ALLOWED_HOSTS",
    "localhost,127.0.0.1,[::1],testserver",
)

# Redirect SETUP_FLAG_FILE into the OS temp dir so test runs never touch
# /config (or D:\\config on Windows). The setup-flag resolver only honours
# paths under /config or $cwd, so we override the env var to a path under
# cwd. Without this, a leftover .setup_completed from a prior run silently
# fails `assert is_setup_completed(db) is False` in the bypass tests.
_test_flag = os.path.join(os.getcwd(), ".pytest_setup_flag")
os.environ.setdefault("SETUP_FLAG_FILE", _test_flag)
try:
    if os.path.exists(_test_flag):
        os.remove(_test_flag)
except OSError:
    pass

# Don't seed default templates during tests — every call to add_template
# does a real network fetch to GitHub, which would slow the suite down and
# tie test outcomes to GitHub's uptime. Tests that exercise the seed path
# stub get_settings() themselves.
os.environ.setdefault("YACHT_DEFAULT_TEMPLATE_URLS", "")


# --- Shared async DB fixtures ----------------------------------------------
#
# A single in-memory async SQLite engine shared across tests. Each test that
# needs a clean DB should use the `db` fixture (or a session-scoped fixture)
# which drops/recreates all tables, then yields an AsyncSession.
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


@pytest_asyncio.fixture
async def db():
    """Async SQLAlchemy session on an in-memory SQLite DB.

    Drops and recreates all tables before each test so the session starts
    clean. Replaces the old sync `db` fixtures in migrated test files.
    """
    from api.db.database import Base
    async with _ASYNC_TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with _ASYNC_TEST_SESSION() as session:
        yield session


@pytest_asyncio.fixture
async def db_session(db):
    """Alias of `db` for tests that named their fixture `db_session`."""
    return db


@pytest.fixture(autouse=True)
def _mock_authz_helpers(monkeypatch):
    """Most unit tests exercise handler routing/sanitization, not AuthZ.

    `check_permission` (used by container action handlers) now hits the
    database, so it is patched to a no-op by default. Tests that explicitly
    cover authorization can override this patch. `require_superuser` is
    intentionally NOT mocked here so that superuser-gate tests remain real.
    """
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "api.routers.containers.check_permission",
        AsyncMock(return_value=None),
    )
