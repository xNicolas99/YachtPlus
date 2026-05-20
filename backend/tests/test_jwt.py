import pytest
from datetime import timedelta, datetime, timezone
import jwt
from fastapi import HTTPException, Request, Response

from api.auth.jwt import (
    create_access_token,
    get_secret_key,
    ALGORITHM,
    verify_token,
    get_current_user_token,
    get_current_user,
    AuthWrapper,
    get_auth_wrapper,
    TokenData
)
from api.settings import Settings
import api.auth.jwt as jwt_module

settings = Settings()

def test_get_secret_key(monkeypatch):
    monkeypatch.setattr(jwt_module.settings, "SECRET_KEY", "test_secret_key")
    assert get_secret_key() == "test_secret_key"

def test_create_access_token_default_expiration():
    data = {"sub": "testuser"}
    token = create_access_token(data)

    decoded = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])

    assert decoded["sub"] == "testuser"
    assert "exp" in decoded

def test_create_access_token_custom_expiration():
    data = {"sub": "testuser"}
    expires_delta = timedelta(minutes=30)
    token = create_access_token(data, expires_delta=expires_delta)

    decoded = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])

    assert decoded["sub"] == "testuser"
    assert "exp" in decoded

def test_verify_token_success():
    data = {"sub": "testuser", "setup_pending": True}
    token = create_access_token(data)
    credentials_exception = HTTPException(status_code=401, detail="Invalid")

    token_data = verify_token(token, credentials_exception)
    assert token_data.username == "testuser"
    assert token_data.setup_pending is True

def test_verify_token_missing_sub():
    data = {"setup_pending": True}
    token = create_access_token(data)
    credentials_exception = HTTPException(status_code=401, detail="Invalid")
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

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Invalid"

def test_verify_token_invalid_signature():
    token = jwt.encode({"sub": "testuser"}, "wrong_secret_thats_long_enough", algorithm=ALGORITHM)
    credentials_exception = HTTPException(status_code=401, detail="Invalid")
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

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Invalid"

class MockRequest:
    def __init__(self, headers=None, cookies=None):
        self.headers = headers or {}
        self.cookies = cookies or {}

def test_get_current_user_token_from_header():
    request = MockRequest(headers={"Authorization": "Bearer testtoken"})
    assert get_current_user_token(request) == "testtoken"

def test_get_current_user_token_from_cookie():
    request = MockRequest(cookies={"access_token_cookie": "cookietoken"})
    assert get_current_user_token(request) == "cookietoken"

def test_get_current_user_token_none():
    request = MockRequest()
    assert get_current_user_token(request) is None

def test_get_current_user_auth_disabled(monkeypatch):
    monkeypatch.setattr(jwt_module.settings, "DISABLE_AUTH", "true")
    assert get_current_user("any_token") == "admin"

def test_get_current_user_missing_token(monkeypatch):
    monkeypatch.setattr(jwt_module.settings, "DISABLE_AUTH", "false")
    with pytest.raises(HTTPException) as excinfo:
        get_current_user(None)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Could not validate credentials"

def test_get_current_user_valid_token(monkeypatch):
    monkeypatch.setattr(jwt_module.settings, "DISABLE_AUTH", "false")
    token = create_access_token({"sub": "testuser"})
    user = get_current_user(token)
    assert user.username == "testuser"

class MockResponse:
    def __init__(self):
        self.cookies = {}
        self.deleted_cookies = set()

    def set_cookie(self, key, value, httponly, max_age, samesite, secure):
        self.cookies[key] = {
            "value": value,
            "httponly": httponly,
            "max_age": max_age,
            "samesite": samesite,
            "secure": secure
        }

    def delete_cookie(self, key):
        self.deleted_cookies.add(key)

def test_auth_wrapper_jwt_required(monkeypatch):
    monkeypatch.setattr(jwt_module.settings, "DISABLE_AUTH", "false")
    token = create_access_token({"sub": "testuser", "setup_pending": False})
    request = MockRequest(headers={"Authorization": f"Bearer {token}"})

    wrapper = AuthWrapper(request)
    user = wrapper.jwt_required()
    assert user.username == "testuser"
    assert wrapper.user == user

def test_auth_wrapper_jwt_required_setup_pending(monkeypatch):
    monkeypatch.setattr(jwt_module.settings, "DISABLE_AUTH", "false")
    token = create_access_token({"sub": "testuser", "setup_pending": True})
    request = MockRequest(headers={"Authorization": f"Bearer {token}"})
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
    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Setup is pending, restricted access"

    # Should work if allow_setup_pending=True
    user = wrapper.jwt_required(allow_setup_pending=True)
    assert user.username == "testuser"

def test_auth_wrapper_get_jwt_subject(monkeypatch):
    monkeypatch.setattr(jwt_module.settings, "DISABLE_AUTH", "false")
    token = create_access_token({"sub": "testuser"})
    request = MockRequest(headers={"Authorization": f"Bearer {token}"})

    wrapper = AuthWrapper(request)
    assert wrapper.get_jwt_subject() == "testuser"

    # Second call should use cached user
    monkeypatch.setattr(jwt_module, "get_current_user_token", lambda req: None)
    assert wrapper.get_jwt_subject() == "testuser"

def test_auth_wrapper_cookies():
    request = MockRequest()
    wrapper = AuthWrapper(request)
    response = MockResponse()

    wrapper.set_access_cookies("newtoken", response, max_age=100)
    assert "access_token_cookie" in response.cookies
    assert response.cookies["access_token_cookie"]["value"] == "newtoken"
    assert response.cookies["access_token_cookie"]["max_age"] == 100

    wrapper.unset_jwt_cookies(response)
    assert "access_token_cookie" in response.deleted_cookies

def test_get_auth_wrapper():
    request = MockRequest()
    wrapper = get_auth_wrapper(request)
    assert isinstance(wrapper, AuthWrapper)
    assert wrapper.request == request

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
from fastapi import Request
from api.auth.jwt import get_current_user_token

def test_get_current_user_token_header():
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {"Authorization": "Bearer test_token"}
    mock_request.cookies = {}
    assert get_current_user_token(mock_request) == "test_token"

def test_get_current_user_token_cookie():
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {}
    mock_request.cookies = {"access_token_cookie": "test_cookie_token"}
    assert get_current_user_token(mock_request) == "test_cookie_token"

def test_get_current_user_token_header_precedence():
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {"Authorization": "Bearer test_token"}
    mock_request.cookies = {"access_token_cookie": "test_cookie_token"}
    assert get_current_user_token(mock_request) == "test_token"

def test_get_current_user_token_invalid_header():
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {"Authorization": "Invalid test_token"}
    mock_request.cookies = {}
    assert get_current_user_token(mock_request) is None

def test_get_current_user_token_missing():
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {}
    mock_request.cookies = {}
    assert get_current_user_token(mock_request) is None
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
