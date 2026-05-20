from unittest.mock import MagicMock
from api.auth.jwt import (
    get_current_user_token,
    get_current_user,
    AuthWrapper,
    get_auth_wrapper
)
import pytest
from datetime import timedelta
from fastapi import HTTPException, status
from api.auth.jwt import verify_token, create_access_token, TokenData


@pytest.fixture
def credentials_exception():
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )


def test_verify_token_valid(credentials_exception):
    token = create_access_token(
        data={"sub": "testuser", "setup_pending": True})
    token_data = verify_token(token, credentials_exception)

    assert isinstance(token_data, TokenData)
    assert token_data.username == "testuser"
    assert token_data.setup_pending is True


def test_verify_token_valid_no_setup_pending(credentials_exception):
    token = create_access_token(data={"sub": "testuser"})
    token_data = verify_token(token, credentials_exception)

    assert isinstance(token_data, TokenData)
    assert token_data.username == "testuser"
    assert token_data.setup_pending is False


def test_verify_token_missing_sub(credentials_exception):
    token = create_access_token(data={"setup_pending": True})

    with pytest.raises(HTTPException) as excinfo:
        verify_token(token, credentials_exception)

    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert excinfo.value.detail == "Could not validate credentials"


def test_verify_token_invalid_token(credentials_exception):
    with pytest.raises(HTTPException) as excinfo:
        verify_token("invalid.token.string", credentials_exception)

    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert excinfo.value.detail == "Could not validate credentials"


def test_verify_token_expired(credentials_exception):
    token = create_access_token(
        data={"sub": "testuser"}, expires_delta=timedelta(minutes=-1))

    with pytest.raises(HTTPException) as excinfo:
        verify_token(token, credentials_exception)

    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert excinfo.value.detail == "Could not validate credentials"


def test_get_current_user_token_header():
    request = MagicMock()
    request.headers.get.return_value = "Bearer valid_token_string"
    assert get_current_user_token(request) == "valid_token_string"


def test_get_current_user_token_cookie():
    request = MagicMock()
    request.headers.get.return_value = None
    request.cookies.get.return_value = "cookie_token_string"
    assert get_current_user_token(request) == "cookie_token_string"


def test_get_current_user_token_none():
    request = MagicMock()
    request.headers.get.return_value = None
    request.cookies.get.return_value = None
    assert get_current_user_token(request) is None


def test_get_current_user_auth_disabled(monkeypatch):
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", True)
    assert get_current_user("any_token") == "admin"


def test_get_current_user_no_token(monkeypatch):
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", False)
    with pytest.raises(HTTPException) as excinfo:
        get_current_user(None)
    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_current_user_valid(monkeypatch):
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", False)
    token = create_access_token(data={"sub": "testuser"})
    user = get_current_user(token)
    assert user.username == "testuser"


def test_auth_wrapper_jwt_required_valid():
    request = MagicMock()
    request.headers.get.return_value = "Bearer " + \
        create_access_token(data={"sub": "testuser"})

    wrapper = AuthWrapper(request)
    user = wrapper.jwt_required()

    assert user.username == "testuser"
    assert wrapper.user == user


def test_auth_wrapper_jwt_required_setup_pending_forbidden():
    request = MagicMock()
    request.headers.get.return_value = "Bearer " + \
        create_access_token(data={"sub": "testuser", "setup_pending": True})

    wrapper = AuthWrapper(request)
    with pytest.raises(HTTPException) as excinfo:
        wrapper.jwt_required()

    assert excinfo.value.status_code == status.HTTP_403_FORBIDDEN
    assert "Setup is pending" in excinfo.value.detail


def test_auth_wrapper_jwt_required_setup_pending_allowed():
    request = MagicMock()
    request.headers.get.return_value = "Bearer " + \
        create_access_token(data={"sub": "testuser", "setup_pending": True})

    wrapper = AuthWrapper(request)
    user = wrapper.jwt_required(allow_setup_pending=True)

    assert user.username == "testuser"


def test_auth_wrapper_get_jwt_subject():
    request = MagicMock()
    request.headers.get.return_value = "Bearer " + \
        create_access_token(data={"sub": "testuser"})

    wrapper = AuthWrapper(request)
    # First call evaluates jwt_required
    assert wrapper.get_jwt_subject() == "testuser"
    # Second call uses cached user
    assert wrapper.get_jwt_subject() == "testuser"


def test_auth_wrapper_unset_jwt_cookies():
    request = MagicMock()
    response = MagicMock()

    wrapper = AuthWrapper(request)
    wrapper.unset_jwt_cookies(response)

    response.delete_cookie.assert_called_once_with("access_token_cookie")


def test_auth_wrapper_set_access_cookies(monkeypatch):
    request = MagicMock()
    response = MagicMock()

    monkeypatch.setattr("api.auth.jwt.settings.ACCESS_TOKEN_EXPIRES", "3600")
    monkeypatch.setattr("api.auth.jwt.settings.SAME_SITE_COOKIES", "lax")
    monkeypatch.setattr("api.auth.jwt.settings.SECURE_COOKIES", True)

    wrapper = AuthWrapper(request)
    wrapper.set_access_cookies("test_token", response)

    response.set_cookie.assert_called_once_with(
        key="access_token_cookie",
        value="test_token",
        httponly=True,
        max_age=3600,
        samesite="lax",
        secure=True
    )


def test_get_auth_wrapper():
    request = MagicMock()
    wrapper = get_auth_wrapper(request)
    assert isinstance(wrapper, AuthWrapper)
    assert wrapper.request == request
