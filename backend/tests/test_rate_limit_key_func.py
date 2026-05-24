"""Regression for BUG-005: every slowapi `key_func` used
`slowapi.util.get_remote_address` which returns `request.client.host`.
Because YachtPlus's own nginx fronts gunicorn on 127.0.0.1, every
request reached the limiter as "127.0.0.1" and the per-route rate
limit was effectively global. One bad actor could burn the budget for
every other user.

The fix routes the key through _resolve_client_ip, which only honours
X-Real-IP / X-Forwarded-For when the direct peer is in TRUSTED_PROXIES
— so spoofed headers from a sibling container still can't dodge the
limit either.
"""
from unittest.mock import MagicMock

from api.utils.security import rate_limit_key


def _request(client_host: str, headers=None):
    req = MagicMock()
    req.client.host = client_host
    req.headers = headers or {}
    return req


def test_falls_back_to_direct_peer_for_untrusted_proxy(monkeypatch):
    monkeypatch.setattr(
        "api.utils.security._settings",
        type("S", (), {"TRUSTED_PROXIES": []})(),
    )
    req = _request("8.8.8.8", headers={"X-Forwarded-For": "1.1.1.1"})
    assert rate_limit_key(req) == "8.8.8.8"


def test_honours_xff_when_peer_trusted(monkeypatch):
    monkeypatch.setattr(
        "api.utils.security._settings",
        type("S", (), {"TRUSTED_PROXIES": ["127.0.0.1"]})(),
    )
    req = _request("127.0.0.1", headers={"X-Forwarded-For": "203.0.113.45"})
    assert rate_limit_key(req) == "203.0.113.45"


def test_xff_ignored_when_peer_not_in_trusted_list(monkeypatch):
    """A sibling container on the same private network (10.0.0.0/8) is
    NOT automatically trusted just because it's private — only the
    explicit list entries are.
    """
    monkeypatch.setattr(
        "api.utils.security._settings",
        type("S", (), {"TRUSTED_PROXIES": ["127.0.0.1"]})(),
    )
    req = _request("10.0.0.5", headers={"X-Forwarded-For": "203.0.113.45"})
    assert rate_limit_key(req) == "10.0.0.5"


def test_cidr_entry_supported(monkeypatch):
    monkeypatch.setattr(
        "api.utils.security._settings",
        type("S", (), {"TRUSTED_PROXIES": ["10.0.0.0/8"]})(),
    )
    req = _request("10.5.5.5", headers={"X-Real-IP": "198.51.100.7"})
    assert rate_limit_key(req) == "198.51.100.7"
