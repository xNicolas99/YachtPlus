import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock
from api.auth.auth import auth_check, auth_check_setup_pending


@pytest.fixture
def mock_settings(monkeypatch):
    # Ensure auth is NOT disabled for these tests
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


def test_auth_check_missing_token(mock_settings):
    # Mock AuthWrapper to simulate missing token (which should raise HTTPException in jwt_required)
    mock_auth = MagicMock()
    mock_auth.jwt_required.side_effect = HTTPException(
        status_code=401, detail="Could not validate credentials")

    with pytest.raises(HTTPException) as excinfo:
        auth_check(mock_auth)

    assert excinfo.value.status_code == 401
    assert "Could not validate credentials" in excinfo.value.detail


def test_auth_check_expired_token(mock_settings):
    # Mock AuthWrapper to simulate expired token
    mock_auth = MagicMock()
    mock_auth.jwt_required.side_effect = HTTPException(
        status_code=401, detail="Signature has expired")

    with pytest.raises(HTTPException) as excinfo:
        auth_check(mock_auth)

    assert excinfo.value.status_code == 401
    assert "Signature has expired" in excinfo.value.detail


def test_auth_check_invalid_signature(mock_settings):
    # Mock AuthWrapper to simulate invalid signature
    mock_auth = MagicMock()
    mock_auth.jwt_required.side_effect = HTTPException(
        status_code=401, detail="Invalid token signature")

    with pytest.raises(HTTPException) as excinfo:
        auth_check(mock_auth)

    assert excinfo.value.status_code == 401
    assert "Invalid token signature" in excinfo.value.detail


def test_auth_check_success(mock_settings):
    # Mock AuthWrapper to simulate successful token validation
    mock_auth = MagicMock()

    # auth_check should return None/pass without raising exception
    auth_check(mock_auth)

    # Ensure jwt_required was called once
    mock_auth.jwt_required.assert_called_once()


def test_auth_check_auth_disabled(monkeypatch):
    # Ensure auth is disabled
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", True)

    mock_auth = MagicMock()

    # auth_check should pass without raising exception
    auth_check(mock_auth)

    # Ensure jwt_required was NOT called because auth is disabled
    mock_auth.jwt_required.assert_not_called()


def test_auth_check_setup_pending_success(mock_settings):
    mock_auth = MagicMock()
    auth_check_setup_pending(mock_auth)
    mock_auth.jwt_required.assert_called_once_with(allow_setup_pending=True)


def test_auth_check_setup_pending_auth_disabled(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", True)
    mock_auth = MagicMock()
    auth_check_setup_pending(mock_auth)
    mock_auth.jwt_required.assert_not_called()


def test_check_permission_auth_disabled(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", True)
    mock_auth = MagicMock()
    mock_db = MagicMock()

    from api.auth.auth import check_permission
    result = check_permission("perm_start", mock_auth, mock_db)
    assert result is True

from sqlalchemy.orm import Session
from api.auth.auth import check_permission
from api.db.models.users import User

def test_check_permission_auth_disabled(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", True)

    mock_auth = MagicMock()
    mock_db = MagicMock(spec=Session)

    assert check_permission("any_permission", mock_auth, mock_db) is True
    mock_auth.get_jwt_subject.assert_not_called()

def test_check_permission_user_not_found(mock_settings):
    mock_auth = MagicMock()
    mock_auth.get_jwt_subject.return_value = "testuser"
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    from api.auth.auth import check_permission
    with pytest.raises(HTTPException) as excinfo:
        check_permission("perm_start", mock_auth, mock_db)

    mock_db = MagicMock(spec=Session)
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as excinfo:
        check_permission("some_permission", mock_auth, mock_db)

    assert excinfo.value.status_code == 401
    assert "User not found" in excinfo.value.detail


def test_check_permission_superuser(mock_settings):
    mock_auth = MagicMock()
    mock_auth.get_jwt_subject.return_value = "testuser"

    from api.db.models.users import User
    mock_user = User(username="testuser", is_superuser=True)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    from api.auth.auth import check_permission
    result = check_permission("perm_start", mock_auth, mock_db)
    assert result is True


def test_check_permission_user_has_perm(mock_settings):
    mock_auth = MagicMock()
    mock_auth.get_jwt_subject.return_value = "testuser"

    from api.db.models.users import User
    mock_user = User(username="testuser", is_superuser=False, perm_start=True)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    from api.auth.auth import check_permission
    result = check_permission("perm_start", mock_auth, mock_db)
    assert result is True


def test_check_permission_user_lacks_perm(mock_settings):
    mock_auth = MagicMock()
    mock_auth.get_jwt_subject.return_value = "testuser"

    from api.db.models.users import User
    mock_user = User(username="testuser", is_superuser=False, perm_start=False)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    from api.auth.auth import check_permission
    with pytest.raises(HTTPException) as excinfo:
        check_permission("perm_start", mock_auth, mock_db)

    assert excinfo.value.status_code == 403
    assert "User lacks permission: perm_start" in excinfo.value.detail


def test_get_db():
    from api.auth.auth import get_db

    db_gen = get_db()
    db = next(db_gen)

    assert db is not None

    with pytest.raises(StopIteration):
        next(db_gen)
def test_check_permission_superuser(mock_settings):
    mock_auth = MagicMock()
    mock_auth.get_jwt_subject.return_value = "adminuser"

    class DummyUser:
        is_superuser = True

    mock_user = DummyUser()

    mock_db = MagicMock(spec=Session)
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    assert check_permission("some_permission", mock_auth, mock_db) is True

def test_check_permission_user_has_permission(mock_settings):
    mock_auth = MagicMock()
    mock_auth.get_jwt_subject.return_value = "normaluser"

    class DummyUser:
        is_superuser = False
        some_permission = True

    mock_user = DummyUser()

    mock_db = MagicMock(spec=Session)
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    assert check_permission("some_permission", mock_auth, mock_db) is True

def test_check_permission_user_lacks_permission(mock_settings):
    mock_auth = MagicMock()
    mock_auth.get_jwt_subject.return_value = "normaluser"

    class DummyUser:
        is_superuser = False
        some_permission = False

    mock_user = DummyUser()

    mock_db = MagicMock(spec=Session)
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    with pytest.raises(HTTPException) as excinfo:
        check_permission("some_permission", mock_auth, mock_db)

    assert excinfo.value.status_code == 403
    assert "User lacks permission: some_permission" in excinfo.value.detail
from unittest.mock import patch, MagicMock
from api.auth.auth import get_db

def test_get_db():
    with patch("api.auth.auth.SessionLocal") as mock_session_local:
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        db_generator = get_db()
        db = next(db_generator)

        assert db == mock_db
        mock_session_local.assert_called_once()
        mock_db.close.assert_not_called()

        try:
            next(db_generator)
        except StopIteration:
            pass

        mock_db.close.assert_called_once()
