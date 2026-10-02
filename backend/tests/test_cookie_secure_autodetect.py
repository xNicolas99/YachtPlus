"""Regression for the LAN/HTTP setup-wizard 401 storm.

The previous SECURE_COOKIES default was `ENVIRONMENT == "production"`,
which marked the access_token_cookie as `Secure` unconditionally on any
non-dev deploy. Browsers refuse to *store* a Secure cookie that arrives
over HTTP, so on a typical http://192.168.x.y LAN deploy the whole
setup flow died at register: no cookie -> 401 on /2fa/generate -> QR
never loaded.

The new behaviour:
  - SECURE_COOKIES=true  -> always Secure (admin opted in, e.g. for an
    HTTPS deploy fronted by their own reverse proxy).
  - SECURE_COOKIES=false -> never Secure.
  - SECURE_COOKIES unset -> per-request auto-detect: Secure only when
    THIS request is HTTPS (or X-Forwarded-Proto says so via the nginx
    in front of us).
"""
import pytest
from unittest.mock import MagicMock

from api.auth.jwt import AuthWrapper


class _Req:
    """Minimal request stand-in: configurable scheme and headers."""
    def __init__(self, scheme="http", headers=None):
        self.url = type("U", (), {"scheme": scheme})()
        self.headers = headers or {}


def _capture():
    """Return a Response double whose set_cookie call we can inspect."""
    resp = MagicMock()
    resp._captured = {}

    def _set_cookie(**kwargs):
        resp._captured.update(kwargs)
    resp.set_cookie.side_effect = _set_cookie
    return resp


def test_http_request_does_not_mark_secure(monkeypatch):
    """Auto mode + plain HTTP -> Secure=False, so the browser actually
    stores the cookie."""
    monkeypatch.setattr("api.auth.jwt.settings.SECURE_COOKIES", None)
    wrapper = AuthWrapper(_Req(scheme="http"))
    resp = _capture()
    wrapper.set_access_cookies("tok", resp)
    assert resp._captured["secure"] is False


def test_https_request_marks_secure(monkeypatch):
    monkeypatch.setattr("api.auth.jwt.settings.SECURE_COOKIES", None)
    wrapper = AuthWrapper(_Req(scheme="https"))
    resp = _capture()
    wrapper.set_access_cookies("tok", resp)
    assert resp._captured["secure"] is True


def test_x_forwarded_proto_https_marks_secure(monkeypatch):
    """Behind nginx the request to gunicorn is always http://, so we
    must honour X-Forwarded-Proto from the trusted local proxy."""
    monkeypatch.setattr("api.auth.jwt.settings.SECURE_COOKIES", None)
    wrapper = AuthWrapper(_Req(scheme="http", headers={"x-forwarded-proto": "https"}))
    resp = _capture()
    wrapper.set_access_cookies("tok", resp)
    assert resp._captured["secure"] is True


def test_x_forwarded_proto_first_hop_wins(monkeypatch):
    """The header can be a comma list when multiple proxies prepend
    their own scheme — the leftmost entry is the original client."""
    monkeypatch.setattr("api.auth.jwt.settings.SECURE_COOKIES", None)
    wrapper = AuthWrapper(_Req(scheme="http", headers={"x-forwarded-proto": "https, http"}))
    resp = _capture()
    wrapper.set_access_cookies("tok", resp)
    assert resp._captured["secure"] is True


def test_explicit_true_forces_secure_even_over_http(monkeypatch):
    """Operators who terminate TLS upstream can still pin Secure=True."""
    monkeypatch.setattr("api.auth.jwt.settings.SECURE_COOKIES", True)
    wrapper = AuthWrapper(_Req(scheme="http"))
    resp = _capture()
    wrapper.set_access_cookies("tok", resp)
    assert resp._captured["secure"] is True


def test_explicit_false_disables_secure_even_over_https(monkeypatch):
    monkeypatch.setattr("api.auth.jwt.settings.SECURE_COOKIES", False)
    wrapper = AuthWrapper(_Req(scheme="https"))
    resp = _capture()
    wrapper.set_access_cookies("tok", resp)
    assert resp._captured["secure"] is False


def test_path_is_root(monkeypatch):
    """The cookie MUST have path=/ so it's sent on /api/auth/2fa/* too;
    without it the browser only sends it back on /api/setup/* and the
    2FA step of the wizard 401s."""
    monkeypatch.setattr("api.auth.jwt.settings.SECURE_COOKIES", None)
    wrapper = AuthWrapper(_Req(scheme="http"))
    resp = _capture()
    wrapper.set_access_cookies("tok", resp)
    assert resp._captured["path"] == "/"
