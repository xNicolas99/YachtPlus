import pytest
from datetime import datetime, timedelta
import jwt
from fastapi import HTTPException, Request, Response
from api.auth.jwt import create_access_token, verify_token, ALGORITHM, TokenData, get_secret_key, get_current_user_token, get_current_user, AuthWrapper, get_auth_wrapper

@pytest.fixture
def mock_secret_key(monkeypatch):
    monkeypatch.setattr("api.auth.jwt.settings.SECRET_KEY", "test_secret_key")

def test_create_access_token(mock_secret_key):
    data = {"sub": "testuser", "setup_pending": False}
    token = create_access_token(data)
    decoded = jwt.decode(token, "test_secret_key", algorithms=[ALGORITHM])
    assert decoded["sub"] == "testuser"
    assert decoded["setup_pending"] is False
    assert "exp" in decoded

def test_create_access_token_custom_expire(mock_secret_key):
    data = {"sub": "testuser"}
    expires_delta = timedelta(minutes=10)
    token = create_access_token(data, expires_delta=expires_delta)
    decoded = jwt.decode(token, "test_secret_key", algorithms=[ALGORITHM])
    assert decoded["sub"] == "testuser"
    assert "exp" in decoded

def test_verify_token_success(mock_secret_key):
    data = {"sub": "testuser", "setup_pending": True}
    token = create_access_token(data)
    credentials_exception = HTTPException(status_code=401, detail="Invalid")
    token_data = verify_token(token, credentials_exception)
    assert isinstance(token_data, TokenData)
    assert token_data.username == "testuser"
    assert token_data.setup_pending is True

def test_verify_token_missing_username(mock_secret_key):
    data = {"setup_pending": False}
    token = create_access_token(data)
    credentials_exception = HTTPException(status_code=401, detail="Missing username")
    with pytest.raises(HTTPException) as excinfo:
        verify_token(token, credentials_exception)
    assert excinfo.value.detail == "Missing username"

def test_verify_token_expired(mock_secret_key):
    data = {"sub": "testuser"}
    token = create_access_token(data, expires_delta=timedelta(minutes=-10))
    credentials_exception = HTTPException(status_code=401, detail="Expired")
    with pytest.raises(HTTPException) as excinfo:
        verify_token(token, credentials_exception)
    assert excinfo.value.detail == "Expired"

def test_verify_token_invalid_signature(mock_secret_key):
    data = {"sub": "testuser"}
    expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode = data.copy()
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, "wrong_secret_key", algorithm=ALGORITHM)
    credentials_exception = HTTPException(status_code=401, detail="Invalid signature")
    with pytest.raises(HTTPException) as excinfo:
        verify_token(token, credentials_exception)
    assert excinfo.value.detail == "Invalid signature"

def test_verify_token_pyjwt_error(mock_secret_key):
    credentials_exception = HTTPException(status_code=401, detail="PyJWT Error")
    with pytest.raises(HTTPException) as excinfo:
        verify_token("invalid.token.string", credentials_exception)
    assert excinfo.value.detail == "PyJWT Error"

def test_get_current_user_token_header():
    request = Request(scope={"type": "http", "headers": [(b"authorization", b"Bearer mytoken")]})
    assert get_current_user_token(request) == "mytoken"

def test_get_current_user_token_cookie():
    request = Request(scope={"type": "http", "headers": [(b"cookie", b"access_token_cookie=mycookie")]})
    assert get_current_user_token(request) == "mycookie"

def test_get_current_user_token_none():
    request = Request(scope={"type": "http", "headers": []})
    assert get_current_user_token(request) is None

def test_get_current_user_auth_disabled(monkeypatch):
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", "True")
    assert get_current_user("sometoken") == "admin"

def test_get_current_user_no_token(monkeypatch):
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", "False")
    with pytest.raises(HTTPException) as excinfo:
        get_current_user(None)
    assert excinfo.value.status_code == 401

def test_get_current_user_success(monkeypatch, mock_secret_key):
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", "False")
    data = {"sub": "testuser", "setup_pending": False}
    token = create_access_token(data)
    token_data = get_current_user(token)
    assert token_data.username == "testuser"
    assert token_data.setup_pending is False

def test_auth_wrapper_jwt_required(monkeypatch, mock_secret_key):
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", "False")
    data = {"sub": "testuser", "setup_pending": False}
    token = create_access_token(data)
    request = Request(scope={"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())]})
    wrapper = AuthWrapper(request)
    token_data = wrapper.jwt_required()
    assert token_data.username == "testuser"
    assert wrapper.user == token_data

def test_auth_wrapper_jwt_required_setup_pending_forbidden(monkeypatch, mock_secret_key):
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", "False")
    data = {"sub": "testuser", "setup_pending": True}
    token = create_access_token(data)
    request = Request(scope={"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())]})
    wrapper = AuthWrapper(request)
    with pytest.raises(HTTPException) as excinfo:
        wrapper.jwt_required(allow_setup_pending=False)
    assert excinfo.value.status_code == 403

def test_auth_wrapper_get_jwt_subject(monkeypatch, mock_secret_key):
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", "False")
    data = {"sub": "testuser", "setup_pending": False}
    token = create_access_token(data)
    request = Request(scope={"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())]})
    wrapper = AuthWrapper(request)
    subject = wrapper.get_jwt_subject()
    assert subject == "testuser"
    subject2 = wrapper.get_jwt_subject()
    assert subject2 == "testuser"

def test_auth_wrapper_unset_jwt_cookies():
    request = Request(scope={"type": "http", "headers": []})
    wrapper = AuthWrapper(request)
    response = Response()
    wrapper.unset_jwt_cookies(response)
    assert 'access_token_cookie' in response.headers.get("set-cookie", "")
    assert 'Max-Age=0' in response.headers.get("set-cookie", "")

def test_auth_wrapper_set_access_cookies():
    request = Request(scope={"type": "http", "headers": []})
    wrapper = AuthWrapper(request)
    response = Response()
    wrapper.set_access_cookies("mytoken", response, max_age=3600)
    assert 'access_token_cookie=mytoken' in response.headers.get("set-cookie", "")

def test_get_auth_wrapper():
    request = Request(scope={"type": "http", "headers": []})
    wrapper = get_auth_wrapper(request)
    assert isinstance(wrapper, AuthWrapper)
    assert wrapper.request == request

def test_get_secret_key(monkeypatch):
    monkeypatch.setattr("api.auth.jwt.settings.SECRET_KEY", "dummy_secret_key")
    assert get_secret_key() == "dummy_secret_key"
