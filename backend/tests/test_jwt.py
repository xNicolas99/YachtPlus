import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from fastapi import Request, Response, HTTPException
import jwt
from api.auth.jwt import (
    get_auth_wrapper,
    AuthWrapper,
    TokenData,
    create_access_token,
    verify_token,
    get_current_user_token,
    get_current_user,
    get_secret_key,
    ALGORITHM
)

def test_get_auth_wrapper():
    """Test that get_auth_wrapper returns an AuthWrapper instance with the correct request."""
    mock_request = MagicMock(spec=Request)
    wrapper = get_auth_wrapper(mock_request)

    assert isinstance(wrapper, AuthWrapper)
    assert wrapper.request == mock_request

def test_create_access_token():
    """Test creating an access token."""
    data = {"sub": "testuser"}
    token = create_access_token(data)

    # Verify the token can be decoded
    payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])
    assert payload["sub"] == "testuser"
    assert "exp" in payload

def test_create_access_token_with_delta():
    """Test creating an access token with a specific expiration delta."""
    data = {"sub": "testuser"}
    delta = timedelta(minutes=5)
    token = create_access_token(data, expires_delta=delta)

    payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])
    assert payload["sub"] == "testuser"

    # Ensure it expires in roughly 5 minutes, handling timezones safely
    exp_time = datetime.utcfromtimestamp(payload["exp"])
    time_diff = exp_time - datetime.utcnow()
    assert timedelta(minutes=4) <= time_diff <= timedelta(minutes=6)

def test_verify_token_success():
    """Test successful token verification."""
    data = {"sub": "testuser", "setup_pending": True}
    token = create_access_token(data)

    exception = HTTPException(status_code=401, detail="Invalid")
    token_data = verify_token(token, exception)

    assert token_data.username == "testuser"
    assert token_data.setup_pending is True

def test_verify_token_missing_sub():
    """Test token verification failure when missing subject."""
    data = {"setup_pending": True} # Missing 'sub'
    token = create_access_token(data)

    exception = HTTPException(status_code=401, detail="Invalid credentials")

    with pytest.raises(HTTPException) as exc_info:
        verify_token(token, exception)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid credentials"

def test_verify_token_invalid_jwt():
    """Test token verification failure with invalid JWT."""
    exception = HTTPException(status_code=401, detail="Invalid token")

    with pytest.raises(HTTPException) as exc_info:
        verify_token("invalid.token.string", exception)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"

def test_get_current_user_token_header():
    """Test getting token from Authorization header."""
    mock_request = MagicMock()
    mock_request.headers.get.return_value = "Bearer my_test_token"

    token = get_current_user_token(mock_request)
    assert token == "my_test_token"

def test_get_current_user_token_cookie():
    """Test getting token from cookie."""
    mock_request = MagicMock()
    mock_request.headers.get.return_value = None
    mock_request.cookies.get.return_value = "cookie_test_token"

    token = get_current_user_token(mock_request)
    assert token == "cookie_test_token"

def test_get_current_user_token_none():
    """Test getting None when no token is present."""
    mock_request = MagicMock()
    mock_request.headers.get.return_value = None
    mock_request.cookies.get.return_value = None

    token = get_current_user_token(mock_request)
    assert token is None

@patch("api.auth.jwt.settings.DISABLE_AUTH", new="True")
def test_get_current_user_auth_disabled():
    """Test get_current_user when auth is disabled."""
    user = get_current_user(token=None)
    assert user == "admin"

@patch("api.auth.jwt.settings.DISABLE_AUTH", new="False")
def test_get_current_user_missing_token():
    """Test get_current_user when token is missing and auth is enabled."""
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token=None)

    assert exc_info.value.status_code == 401

@patch("api.auth.jwt.settings.DISABLE_AUTH", new="False")
def test_get_current_user_valid_token():
    """Test get_current_user with a valid token."""
    data = {"sub": "testuser"}
    token = create_access_token(data)

    token_data = get_current_user(token=token)
    assert token_data.username == "testuser"

@patch("api.auth.jwt.get_current_user_token")
@patch("api.auth.jwt.get_current_user")
def test_auth_wrapper_jwt_required_success(mock_get_current_user, mock_get_current_user_token):
    """Test jwt_required succeeds with valid token."""
    mock_request = MagicMock()
    wrapper = AuthWrapper(mock_request)

    mock_get_current_user_token.return_value = "token"
    mock_token_data = TokenData(username="testuser", setup_pending=False)
    mock_get_current_user.return_value = mock_token_data

    result = wrapper.jwt_required()

    assert result == mock_token_data
    assert wrapper.user == mock_token_data

@patch("api.auth.jwt.get_current_user_token")
@patch("api.auth.jwt.get_current_user")
def test_auth_wrapper_jwt_required_setup_pending_forbidden(mock_get_current_user, mock_get_current_user_token):
    """Test jwt_required raises 403 when setup_pending is True and not allowed."""
    mock_request = MagicMock()
    wrapper = AuthWrapper(mock_request)

    mock_get_current_user_token.return_value = "token"
    mock_token_data = TokenData(username="testuser", setup_pending=True)
    mock_get_current_user.return_value = mock_token_data

    with pytest.raises(HTTPException) as exc_info:
        wrapper.jwt_required(allow_setup_pending=False)

    assert exc_info.value.status_code == 403
    assert "Setup is pending" in exc_info.value.detail

@patch("api.auth.jwt.get_current_user_token")
@patch("api.auth.jwt.get_current_user")
def test_auth_wrapper_jwt_required_setup_pending_allowed(mock_get_current_user, mock_get_current_user_token):
    """Test jwt_required succeeds when setup_pending is True but allowed."""
    mock_request = MagicMock()
    wrapper = AuthWrapper(mock_request)

    mock_get_current_user_token.return_value = "token"
    mock_token_data = TokenData(username="testuser", setup_pending=True)
    mock_get_current_user.return_value = mock_token_data

    result = wrapper.jwt_required(allow_setup_pending=True)

    assert result == mock_token_data
    assert wrapper.user == mock_token_data

def test_auth_wrapper_get_jwt_subject_with_cached_user():
    """Test get_jwt_subject uses cached user if available."""
    mock_request = MagicMock()
    wrapper = AuthWrapper(mock_request)
    wrapper.user = TokenData(username="cacheduser")

    subject = wrapper.get_jwt_subject()
    assert subject == "cacheduser"

@patch.object(AuthWrapper, "jwt_required")
def test_auth_wrapper_get_jwt_subject_without_cached_user(mock_jwt_required):
    """Test get_jwt_subject calls jwt_required if user is not cached."""
    mock_request = MagicMock()
    wrapper = AuthWrapper(mock_request)

    mock_jwt_required.return_value = TokenData(username="fetcheduser")

    subject = wrapper.get_jwt_subject(allow_setup_pending=True)

    assert subject == "fetcheduser"
    mock_jwt_required.assert_called_once_with(allow_setup_pending=True)

def test_auth_wrapper_unset_jwt_cookies():
    """Test unset_jwt_cookies calls response.delete_cookie."""
    mock_request = MagicMock()
    wrapper = AuthWrapper(mock_request)
    mock_response = MagicMock(spec=Response)

    wrapper.unset_jwt_cookies(mock_response)

    mock_response.delete_cookie.assert_called_once_with("access_token_cookie")

@patch("api.auth.jwt.settings.ACCESS_TOKEN_EXPIRES", new="3600")
@patch("api.auth.jwt.settings.SAME_SITE_COOKIES", new="Lax")
@patch("api.auth.jwt.settings.SECURE_COOKIES", new=True)
def test_auth_wrapper_set_access_cookies():
    """Test set_access_cookies calls response.set_cookie with correct params."""
    mock_request = MagicMock()
    wrapper = AuthWrapper(mock_request)
    mock_response = MagicMock(spec=Response)

    token = "test_token"
    wrapper.set_access_cookies(token, mock_response)

    mock_response.set_cookie.assert_called_once_with(
        key="access_token_cookie",
        value=token,
        httponly=True,
        max_age=3600,
        samesite="Lax",
        secure=True
    )

@patch("api.auth.jwt.settings.ACCESS_TOKEN_EXPIRES", new="3600")
@patch("api.auth.jwt.settings.SAME_SITE_COOKIES", new="Lax")
@patch("api.auth.jwt.settings.SECURE_COOKIES", new=True)
def test_auth_wrapper_set_access_cookies_custom_max_age():
    """Test set_access_cookies with custom max_age."""
    mock_request = MagicMock()
    wrapper = AuthWrapper(mock_request)
    mock_response = MagicMock(spec=Response)

    token = "test_token"
    wrapper.set_access_cookies(token, mock_response, max_age=7200)

    mock_response.set_cookie.assert_called_once_with(
        key="access_token_cookie",
        value=token,
        httponly=True,
        max_age=7200,
        samesite="Lax",
        secure=True
    )
