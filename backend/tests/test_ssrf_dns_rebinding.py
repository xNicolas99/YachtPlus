"""Regression for BUG-002: validate_url resolved the hostname ONCE, then
urllib.request resolved it AGAIN at connect time. A DNS-rebinding attacker
controlling their own zone could return a public IP for the first lookup
(passes validation) and 127.0.0.1 / 169.254.169.254 / a sibling-container
IP for the second (the actual connection).

The fix is a custom HTTPConnection/HTTPSConnection that re-runs the
private-IP check from inside connect(), eliminating the TOCTOU window.
"""
from unittest.mock import patch

import pytest

from api.db.crud.templates import (
    _SSRFGuardedHTTPConnection,
    _SSRFGuardedHTTPSConnection,
    _SSRFBlocked,
    _check_address_safe,
)


def _fake_getaddrinfo(_host, _port, **_kw):
    return _fake_getaddrinfo.next_return


def test_check_address_safe_blocks_private_ip():
    with patch(
        "api.db.crud.templates.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("127.0.0.1", 80))],
    ):
        with pytest.raises(_SSRFBlocked) as exc:
            _check_address_safe("evil.example", 80)
    assert "private IP" in str(exc.value)


def test_check_address_safe_blocks_link_local():
    """AWS / GCP / Azure instance metadata lives on 169.254.169.254 —
    one of the classic SSRF targets."""
    with patch(
        "api.db.crud.templates.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("169.254.169.254", 80))],
    ):
        with pytest.raises(_SSRFBlocked):
            _check_address_safe("evil.example", 80)


def test_check_address_safe_blocks_when_any_resolved_ip_is_private():
    """getaddrinfo can return multiple IPs; reject if ANY of them is
    private — an attacker can pad the list with public decoys."""
    with patch(
        "api.db.crud.templates.socket.getaddrinfo",
        return_value=[
            (2, 1, 6, "", ("93.184.216.34", 80)),
            (2, 1, 6, "", ("10.0.0.5", 80)),
        ],
    ):
        with pytest.raises(_SSRFBlocked):
            _check_address_safe("evil.example", 80)


def test_check_address_safe_allows_public_ip():
    with patch(
        "api.db.crud.templates.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("93.184.216.34", 80))],
    ):
        # Should not raise.
        _check_address_safe("example.com", 80)


def test_check_address_safe_blocks_on_resolution_failure():
    import socket as _socket
    with patch(
        "api.db.crud.templates.socket.getaddrinfo",
        side_effect=_socket.gaierror("no such host"),
    ):
        with pytest.raises(_SSRFBlocked):
            _check_address_safe("nx.example", 80)


def test_check_address_safe_blocks_on_empty_resolution():
    with patch(
        "api.db.crud.templates.socket.getaddrinfo",
        return_value=[],
    ):
        with pytest.raises(_SSRFBlocked):
            _check_address_safe("nx.example", 80)


def test_guarded_http_connection_rejects_rebind():
    """End-to-end-ish: simulate the rebind by patching socket.getaddrinfo
    AFTER validate_url would have run. The custom HTTPConnection should
    refuse to open the socket."""
    conn = _SSRFGuardedHTTPConnection("evil.example", 80, timeout=1)
    with patch(
        "api.db.crud.templates.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("127.0.0.1", 80))],
    ):
        with pytest.raises(_SSRFBlocked):
            conn.connect()


def test_guarded_https_connection_rejects_rebind():
    conn = _SSRFGuardedHTTPSConnection("evil.example", 443, timeout=1)
    with patch(
        "api.db.crud.templates.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("169.254.169.254", 443))],
    ):
        with pytest.raises(_SSRFBlocked):
            conn.connect()


def test_ssrf_blocked_is_oserror_subclass():
    """The guarded connection raises _SSRFBlocked, but urllib only catches
    OSError for transport failures — make sure the inheritance is right
    so the request layer maps it to a normal 400 instead of leaking a
    500-class internal error."""
    assert issubclass(_SSRFBlocked, OSError)
