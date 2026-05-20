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

    with pytest.raises(HTTPException) as excinfo:
        verify_token(token, credentials_exception)

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Invalid"

def test_verify_token_invalid_signature():
    token = jwt.encode({"sub": "testuser"}, "wrong_secret_thats_long_enough", algorithm=ALGORITHM)
    credentials_exception = HTTPException(status_code=401, detail="Invalid")

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
