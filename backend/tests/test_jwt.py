import pytest
from datetime import datetime, timedelta, timezone
import jwt
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, Request, Response

from api.auth.jwt import (
    create_access_token,
    verify_token,
    ALGORITHM,
    TokenData,
    get_secret_key,
    get_current_user_token,
    get_current_user,
    AuthWrapper,
    get_auth_wrapper,
)


@pytest.fixture
def mock_secret_key(monkeypatch):
    monkeypatch.setattr(
        "api.auth.jwt.settings.SECRET_KEY",
        "test_secret_key_12345678901234567890123456789012",  # 32+ bytes
    )


def test_get_secret_key(monkeypatch):
    monkeypatch.setattr(
        "api.auth.jwt.settings.SECRET_KEY",
        "dummy_secret_key_12345678901234567890123456789012",  # 32+ bytes
    )
    assert get_secret_key() == "dummy_secret_key_12345678901234567890123456789012"


def test_get_auth_wrapper():
    mock_request = MagicMock(spec=Request)
    wrapper = get_auth_wrapper(mock_request)
    assert isinstance(wrapper, AuthWrapper)
    assert wrapper.request == mock_request


def test_create_access_token(mock_secret_key):
    data = {"sub": "testuser", "setup_pending": False}
    token = create_access_token(data)
    decoded = jwt.decode(
        token,
        "test_secret_key_12345678901234567890123456789012",
        algorithms=[ALGORITHM],
    )
    assert decoded["sub"] == "testuser"
    assert decoded["setup_pending"] is False
    assert "exp" in decoded
    assert "jti" in decoded


def test_create_access_token_custom_expire(mock_secret_key):
    data = {"sub": "testuser"}
    expires_delta = timedelta(minutes=10)
    token = create_access_token(data, expires_delta=expires_delta)
    decoded = jwt.decode(
        token,
        "test_secret_key_12345678901234567890123456789012",
        algorithms=[ALGORITHM],
    )
    assert decoded["sub"] == "testuser"
    assert "exp" in decoded


@pytest.mark.asyncio
async def test_verify_token_success(mock_secret_key):
    data = {"sub": "testuser", "setup_pending": True}
    token = create_access_token(data)
    credentials_exception = HTTPException(status_code=401, detail="Invalid")
    token_data = await verify_token(token, credentials_exception)
    assert isinstance(token_data, TokenData)
    assert token_data.username == "testuser"
    assert token_data.setup_pending is True


@pytest.mark.asyncio
async def test_verify_token_missing_username(mock_secret_key):
    data = {"setup_pending": False}
    token = create_access_token(data)
    credentials_exception = HTTPException(status_code=401, detail="Missing username")
    with pytest.raises(HTTPException) as excinfo:
        await verify_token(token, credentials_exception)
    assert excinfo.value.detail == "Missing username"


@pytest.mark.asyncio
async def test_verify_token_expired(mock_secret_key):
    data = {"sub": "testuser"}
    token = create_access_token(data, expires_delta=timedelta(minutes=-10))
    credentials_exception = HTTPException(status_code=401, detail="Expired")
    with pytest.raises(HTTPException) as excinfo:
        await verify_token(token, credentials_exception)
    assert excinfo.value.detail == "Expired"


@pytest.mark.asyncio
async def test_verify_token_invalid_signature(mock_secret_key):
    data = {"sub": "testuser"}
    expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode = data.copy()
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, "wrong_secret_key_123456789012345678901234567890", algorithm=ALGORITHM)
    credentials_exception = HTTPException(status_code=401, detail="Invalid signature")
    with pytest.raises(HTTPException) as excinfo:
        await verify_token(token, credentials_exception)
    assert excinfo.value.detail == "Invalid signature"


@pytest.mark.asyncio
async def test_verify_token_pyjwt_error(mock_secret_key):
    credentials_exception = HTTPException(status_code=401, detail="Invalid")
    with pytest.raises(HTTPException):
        await verify_token("invalid.token.string", credentials_exception)


def test_get_current_user_token_header():
    request = MagicMock(spec=Request)
    request.headers = {"Authorization": "Bearer abc123"}
    request.cookies = {}
    assert get_current_user_token(request) == "abc123"


def test_get_current_user_token_cookie():
    request = MagicMock(spec=Request)
    request.headers = {}
    request.cookies = {"access_token_cookie": "cookie_token"}
    assert get_current_user_token(request) == "cookie_token"


def test_get_current_user_token_none():
    request = MagicMock(spec=Request)
    request.headers = {}
    request.cookies = {}
    assert get_current_user_token(request) is None


@pytest.mark.asyncio
async def test_get_current_user_auth_disabled(monkeypatch):
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", True)
    assert await get_current_user("sometoken") == "admin"


@pytest.mark.asyncio
async def test_get_current_user_no_token(monkeypatch, mock_secret_key):
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", False)
    with pytest.raises(HTTPException) as excinfo:
        await get_current_user(None)
    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_success(monkeypatch, mock_secret_key):
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", False)
    token = create_access_token({"sub": "testuser"})
    token_data = await get_current_user(token)
    assert isinstance(token_data, TokenData)
    assert token_data.username == "testuser"


@pytest.mark.asyncio
async def test_auth_wrapper_jwt_required(monkeypatch, mock_secret_key):
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", False)
    request = MagicMock(spec=Request)
    request.headers = {}
    request.cookies = {"access_token_cookie": create_access_token({"sub": "testuser"})}
    wrapper = AuthWrapper(request)
    user = await wrapper.jwt_required()
    assert user.username == "testuser"


@pytest.mark.asyncio
async def test_auth_wrapper_jwt_required_setup_pending_forbidden(monkeypatch, mock_secret_key):
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", False)
    request = MagicMock(spec=Request)
    request.headers = {}
    request.cookies = {"access_token_cookie": create_access_token({"sub": "u", "setup_pending": True})}
    wrapper = AuthWrapper(request)
    with pytest.raises(HTTPException) as excinfo:
        await wrapper.jwt_required(allow_setup_pending=False)
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_auth_wrapper_get_jwt_subject(monkeypatch, mock_secret_key):
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", False)
    request = MagicMock(spec=Request)
    request.headers = {}
    request.cookies = {"access_token_cookie": create_access_token({"sub": "testuser"})}
    wrapper = AuthWrapper(request)
    subject = await wrapper.get_jwt_subject()
    assert subject == "testuser"


def test_auth_wrapper_unset_jwt_cookies():
    request = MagicMock(spec=Request)
    wrapper = AuthWrapper(request)
    response = MagicMock(spec=Response)
    wrapper.unset_jwt_cookies(response)
    response.delete_cookie.assert_called_once_with("access_token_cookie", path="/")


def test_auth_wrapper_set_access_cookies():
    request = MagicMock(spec=Request)
    wrapper = AuthWrapper(request)
    response = MagicMock(spec=Response)
    wrapper.set_access_cookies("sometoken", response)
    response.set_cookie.assert_called_once()
