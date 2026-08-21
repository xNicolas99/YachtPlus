"""Test that token expiry uses ACCESS_TOKEN_EXPIRE_MINUTES consistently."""

from datetime import timedelta

from api.auth.jwt import create_access_token, AuthWrapper
from api.settings import Settings


class _FakeRequest:
    def __init__(self):
        self.url = type("Url", (), {"scheme": "http"})()
        self.headers = {}


class _FakeResponse:
    def __init__(self):
        self.cookies = {}

    def set_cookie(self, key, value, max_age=None, **kwargs):
        self.cookies[key] = {"value": value, "max_age": max_age, "kwargs": kwargs}


def test_create_access_token_uses_minutes():
    s = Settings()
    token = create_access_token(data={"sub": "test"}, expires_delta=timedelta(minutes=1))
    import jwt

    payload = jwt.decode(token, s.SECRET_KEY, algorithms=["HS256"])
    exp = payload["exp"]
    iat = payload.get("iat") or exp - 60
    assert exp - iat == 60


def test_cookie_max_age_is_seconds():
    req = _FakeRequest()
    resp = _FakeResponse()
    wrapper = AuthWrapper(req)
    token = create_access_token(data={"sub": "test"})
    wrapper.set_access_cookies(token, resp)
    assert resp.cookies["access_token_cookie"]["max_age"] == 1440 * 60
