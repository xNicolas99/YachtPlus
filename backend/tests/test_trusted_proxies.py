"""Regression for BUG-006: client-IP attribution trusted any private peer's
proxy headers, letting same-LAN attackers spoof their IP.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from api.utils.security import check_ip_restriction, _resolve_client_ip


def _request(host, headers=None):
    req = MagicMock(spec=Request)
    req.client.host = host
    req.headers = headers or {}
    return req


def _settings_with(proxies):
    return type("S", (), {"TRUSTED_PROXIES": list(proxies)})()


def test_xff_ignored_when_no_trusted_proxies():
    with patch("api.utils.security._settings", _settings_with([])):
        ip = _resolve_client_ip(_request("10.0.0.5", {"X-Forwarded-For": "9.9.9.9"}))
    assert ip == "10.0.0.5"


def test_real_ip_ignored_when_peer_not_in_trusted_proxies():
    with patch("api.utils.security._settings", _settings_with(["192.168.1.1"])):
        ip = _resolve_client_ip(_request("10.0.0.5", {"X-Real-IP": "9.9.9.9"}))
    assert ip == "10.0.0.5"


def test_real_ip_honoured_when_peer_is_trusted_proxy():
    with patch("api.utils.security._settings", _settings_with(["10.0.0.5"])):
        ip = _resolve_client_ip(_request("10.0.0.5", {"X-Real-IP": "9.9.9.9"}))
    assert ip == "9.9.9.9"


def test_cidr_match_in_trusted_proxies():
    with patch("api.utils.security._settings", _settings_with(["10.0.0.0/8"])):
        ip = _resolve_client_ip(_request("10.1.2.3", {"X-Real-IP": "9.9.9.9"}))
    assert ip == "9.9.9.9"


def test_invalid_trusted_proxy_entry_skipped():
    # A garbage entry shouldn't blow up the request path.
    with patch("api.utils.security._settings", _settings_with(["not-an-ip", "10.0.0.5"])):
        ip = _resolve_client_ip(_request("10.0.0.5", {"X-Real-IP": "9.9.9.9"}))
    assert ip == "9.9.9.9"


def test_xff_walked_right_to_left_when_proxy_trusted():
    with patch("api.utils.security._settings", _settings_with(["10.0.0.1"])):
        ip = _resolve_client_ip(
            _request("10.0.0.1", {"X-Forwarded-For": "1.1.1.1, 10.0.0.50"})
        )
    assert ip == "1.1.1.1"  # rightmost non-private hop


def test_check_ip_restriction_uses_direct_peer_without_trusted_proxy():
    """End-to-end: attacker on a private peer can't dodge per-IP fail2ban by
    rotating X-Real-IP because their direct peer is what we count against."""
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 0

    with patch("api.utils.security._settings", _settings_with([])):
        ip = check_ip_restriction(
            _request("10.0.0.5", {"X-Real-IP": "10.99.99.99"}),
            db,
        )
    assert ip == "10.0.0.5"


def test_public_peer_with_real_ip_header_still_blocked():
    """No public-peer escape hatch — the peer is what counts."""
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 0
    db.query.return_value.first.return_value = MagicMock(sender_email="x@x")
    with patch("api.utils.security._settings", _settings_with([])):
        with pytest.raises(HTTPException) as exc:
            check_ip_restriction(
                _request("8.8.8.8", {"X-Real-IP": "10.0.0.1"}),
                db,
            )
    assert exc.value.status_code == 403
