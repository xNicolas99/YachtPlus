import pytest
from fastapi import Request, HTTPException, status
from unittest.mock import MagicMock, patch
from api.auth.jwt import get_current_user_token, get_current_user, TokenData

@pytest.fixture
def mock_request():
    return MagicMock(spec=Request)

@pytest.fixture
def mock_settings(monkeypatch):
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", False)

def test_get_current_user_token_from_header(mock_request):
    mock_request.headers = {"Authorization": "Bearer my_secret_token"}
    mock_request.cookies = {}
    token = get_current_user_token(mock_request)
    assert token == "my_secret_token"

def test_get_current_user_token_from_cookie(mock_request):
    mock_request.headers = {}
    mock_request.cookies = {"access_token_cookie": "my_cookie_token"}
    token = get_current_user_token(mock_request)
    assert token == "my_cookie_token"

def test_get_current_user_token_none(mock_request):
    mock_request.headers = {}
    mock_request.cookies = {}
    token = get_current_user_token(mock_request)
    assert token is None

def test_get_current_user_disabled_auth(monkeypatch):
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", "True")
    user = get_current_user(token=None)
    assert user == "admin"

@patch("api.auth.jwt.verify_token")
def test_get_current_user_valid_token(mock_verify_token, mock_settings):
    mock_token_data = TokenData(username="testuser")
    mock_verify_token.return_value = mock_token_data

    user = get_current_user(token="valid_token")

    assert user == mock_token_data
    mock_verify_token.assert_called_once()

def test_get_current_user_missing_token(mock_settings):
    with pytest.raises(HTTPException) as excinfo:
        get_current_user(token=None)

    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert excinfo.value.detail == "Could not validate credentials"
