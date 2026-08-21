"""Async tests for api.auth.auth helpers.

Covers auth_check, auth_check_setup_pending, check_permission,
require_superuser and the shared async get_db dependency.
All DB-facing helpers are mocked with AsyncSession-style mocks
(execute + scalars().first()).
"""
import pytest
import pytest_asyncio
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock

from api.auth import auth as auth_mod
from api.auth.auth import (
    auth_check,
    auth_check_setup_pending,
    check_permission,
    require_superuser,
)
from api.db.models.users import User


@pytest.fixture
def mock_settings(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


class MockAuth:
    """AuthWrapper-compatible mock with async jwt_required / get_jwt_subject."""

    def __init__(self, username=None, raise_on_required=None):
        self.username = username
        self._raise_on_required = raise_on_required
        self.jwt_required = AsyncMock()
        self.get_jwt_subject = AsyncMock(return_value=username)
        if raise_on_required:
            self.jwt_required.side_effect = raise_on_required


@pytest.mark.asyncio
async def test_auth_check_missing_token(mock_settings):
    exc = HTTPException(status_code=401, detail="Could not validate credentials")
    mock_auth = MockAuth(raise_on_required=exc)
    with pytest.raises(HTTPException) as excinfo:
        await auth_check(mock_auth)
    assert excinfo.value.status_code == 401
    assert "Could not validate credentials" in excinfo.value.detail
    mock_auth.jwt_required.assert_awaited_once_with(allow_setup_pending=False)


@pytest.mark.asyncio
async def test_auth_check_expired_token(mock_settings):
    exc = HTTPException(status_code=401, detail="Signature has expired")
    mock_auth = MockAuth(raise_on_required=exc)
    with pytest.raises(HTTPException) as excinfo:
        await auth_check(mock_auth)
    assert excinfo.value.status_code == 401
    assert "Signature has expired" in excinfo.value.detail


@pytest.mark.asyncio
async def test_auth_check_invalid_signature(mock_settings):
    exc = HTTPException(status_code=401, detail="Invalid token signature")
    mock_auth = MockAuth(raise_on_required=exc)
    with pytest.raises(HTTPException) as excinfo:
        await auth_check(mock_auth)
    assert excinfo.value.status_code == 401
    assert "Invalid token signature" in excinfo.value.detail


@pytest.mark.asyncio
async def test_auth_check_success(mock_settings):
    mock_auth = MockAuth()
    await auth_check(mock_auth)
    mock_auth.jwt_required.assert_awaited_once_with(allow_setup_pending=False)


@pytest.mark.asyncio
async def test_auth_check_auth_disabled(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", True)
    mock_auth = MockAuth()
    await auth_check(mock_auth)
    mock_auth.jwt_required.assert_not_called()


@pytest.mark.asyncio
async def test_auth_check_setup_pending_success(mock_settings, monkeypatch):
    mock_auth = MockAuth()
    mock_db = MagicMock()
    monkeypatch.setattr(
        "api.routers.setup.setup.is_setup_completed_async", AsyncMock(return_value=False)
    )
    await auth_check_setup_pending(mock_auth, mock_db)
    mock_auth.jwt_required.assert_awaited_once_with(allow_setup_pending=True)


@pytest.mark.asyncio
async def test_auth_check_setup_pending_blocked_after_setup_complete(
    mock_settings, monkeypatch
):
    mock_auth = MockAuth()
    mock_db = MagicMock()
    monkeypatch.setattr(
        "api.routers.setup.setup.is_setup_completed_async", AsyncMock(return_value=True)
    )
    await auth_check_setup_pending(mock_auth, mock_db)
    mock_auth.jwt_required.assert_awaited_once_with(allow_setup_pending=False)


@pytest.mark.asyncio
async def test_auth_check_setup_pending_auth_disabled(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", True)
    mock_auth = MockAuth()
    mock_db = MagicMock()
    await auth_check_setup_pending(mock_auth, mock_db)
    mock_auth.jwt_required.assert_not_called()


# ---------------------------------------------------------------------------
# check_permission
# ---------------------------------------------------------------------------

def _make_async_db_mock(user=None):
    """Return an AsyncSession-style mock that yields `user` from a select."""
    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = user
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db


@pytest.mark.asyncio
async def test_check_permission_auth_disabled(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", True)
    mock_auth = MockAuth(username="anyuser")
    mock_db = _make_async_db_mock()
    result = await check_permission("perm_start", mock_auth, mock_db)
    assert result is True
    mock_auth.get_jwt_subject.assert_not_called()
    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_check_permission_user_not_found(mock_settings):
    mock_auth = MockAuth(username="testuser")
    mock_db = _make_async_db_mock(user=None)
    with pytest.raises(HTTPException) as excinfo:
        await check_permission("perm_start", mock_auth, mock_db)
    assert excinfo.value.status_code == 401
    assert "User not found" in excinfo.value.detail


@pytest.mark.asyncio
async def test_check_permission_superuser(mock_settings):
    mock_auth = MockAuth(username="testuser")
    mock_user = User(username="testuser", is_superuser=True)
    mock_db = _make_async_db_mock(user=mock_user)
    result = await check_permission("perm_start", mock_auth, mock_db)
    assert result is True


@pytest.mark.asyncio
async def test_check_permission_user_has_permission(mock_settings):
    mock_auth = MockAuth(username="normaluser")

    class DummyUser:
        is_superuser = False
        some_permission = True

    mock_db = _make_async_db_mock(user=DummyUser())
    result = await check_permission("some_permission", mock_auth, mock_db)
    assert result is True


@pytest.mark.asyncio
async def test_check_permission_user_lacks_permission(mock_settings):
    mock_auth = MockAuth(username="normaluser")

    class DummyUser:
        is_superuser = False
        some_permission = False

    mock_db = _make_async_db_mock(user=DummyUser())
    with pytest.raises(HTTPException) as excinfo:
        await check_permission("some_permission", mock_auth, mock_db)
    assert excinfo.value.status_code == 403
    assert "User lacks permission: some_permission" in excinfo.value.detail


# ---------------------------------------------------------------------------
# require_superuser
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_require_superuser_returns_synthetic_user_when_auth_disabled(
    monkeypatch,
):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", True)
    mock_auth = MockAuth(username="testuser")
    mock_db = _make_async_db_mock()
    user = await require_superuser(mock_auth, mock_db)
    assert user.id == 0
    assert user.username == "dev"
    assert user.is_superuser is True


@pytest.mark.asyncio
async def test_require_superuser_user_not_found(mock_settings):
    mock_auth = MockAuth(username="testuser")
    mock_db = _make_async_db_mock(user=None)
    with pytest.raises(HTTPException) as excinfo:
        await require_superuser(mock_auth, mock_db)
    assert excinfo.value.status_code == 401
    assert "User not found or deleted" in excinfo.value.detail


@pytest.mark.asyncio
async def test_require_superuser_non_superuser(mock_settings):
    mock_auth = MockAuth(username="testuser")
    mock_user = User(username="testuser", is_superuser=False)
    mock_db = _make_async_db_mock(user=mock_user)
    with pytest.raises(HTTPException) as excinfo:
        await require_superuser(mock_auth, mock_db)
    assert excinfo.value.status_code == 403
    assert "Superuser required." in excinfo.value.detail


@pytest.mark.asyncio
async def test_require_superuser_success(mock_settings):
    mock_auth = MockAuth(username="admin")
    mock_user = User(username="admin", is_superuser=True)
    mock_db = _make_async_db_mock(user=mock_user)
    user = await require_superuser(mock_auth, mock_db)
    assert user == mock_user


# ---------------------------------------------------------------------------
# get_db dependency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_db():
    from api.utils.auth import get_db

    db_gen = get_db()
    db = await db_gen.__anext__()
    assert db is not None

    with pytest.raises(StopAsyncIteration):
        await db_gen.__anext__()
