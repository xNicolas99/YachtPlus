"""Ensure rate-limiting and IP checks don't crash when request.client is None."""

from unittest.mock import MagicMock

from api.utils.security import _resolve_client_ip, rate_limit_key


def _request_with(client=None, headers=None):
    req = MagicMock()
    req.client = client
    req.headers = headers or {}
    return req


def test_resolve_client_ip_with_none_client():
    req = _request_with(client=None)
    assert _resolve_client_ip(req) == "127.0.0.1"


def test_rate_limit_key_with_none_client():
    req = _request_with(client=None)
    # Should not raise; returns a deterministic key.
    key = rate_limit_key(req)
    assert isinstance(key, str)
    assert "127.0.0.1" in key


def test_resolve_client_ip_with_real_client():
    client = MagicMock()
    client.host = "192.168.1.42"
    req = _request_with(client=client)
    assert _resolve_client_ip(req) == "192.168.1.42"
