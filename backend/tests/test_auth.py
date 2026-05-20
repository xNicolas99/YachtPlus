import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock
from api.auth.auth import auth_check
from api.settings import Settings

@pytest.fixture
def mock_settings(monkeypatch):
    # Ensure auth is NOT disabled for these tests
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)

def test_auth_check_missing_token(mock_settings):
    # Mock AuthWrapper to simulate missing token (which should raise HTTPException in jwt_required)
    mock_auth = MagicMock()
    mock_auth.jwt_required.side_effect = HTTPException(status_code=401, detail="Could not validate credentials")

    with pytest.raises(HTTPException) as excinfo:
        auth_check(mock_auth)

    assert excinfo.value.status_code == 401
    assert "Could not validate credentials" in excinfo.value.detail

def test_auth_check_expired_token(mock_settings):
    # Mock AuthWrapper to simulate expired token
    mock_auth = MagicMock()
    mock_auth.jwt_required.side_effect = HTTPException(status_code=401, detail="Signature has expired")

    with pytest.raises(HTTPException) as excinfo:
        auth_check(mock_auth)

    assert excinfo.value.status_code == 401
    assert "Signature has expired" in excinfo.value.detail

def test_auth_check_invalid_signature(mock_settings):
    # Mock AuthWrapper to simulate invalid signature
    mock_auth = MagicMock()
    mock_auth.jwt_required.side_effect = HTTPException(status_code=401, detail="Invalid token signature")

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
