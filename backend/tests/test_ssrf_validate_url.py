"""Regression for BUG-005: validate_url only caught socket.gaierror.

Anything else (socket.herror, socket.timeout, generic OSError) used to
propagate up unchanged AND, more dangerously, an *empty* getaddrinfo
result list fell through to `return True` without ever raising. Both
modes are now fail-closed.
"""
import socket
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.db.crud.templates import validate_url


@patch("socket.getaddrinfo")
def test_gaierror_raises_400(mock_getaddrinfo):
    mock_getaddrinfo.side_effect = socket.gaierror("no such host")
    with pytest.raises(HTTPException) as exc:
        validate_url("http://nope.invalid/x")
    assert exc.value.status_code == 400
    assert "gaierror" in exc.value.detail


@patch("socket.getaddrinfo")
def test_herror_raises_400(mock_getaddrinfo):
    mock_getaddrinfo.side_effect = socket.herror("host err")
    with pytest.raises(HTTPException) as exc:
        validate_url("http://nope.invalid/x")
    assert exc.value.status_code == 400
    assert "herror" in exc.value.detail


@patch("socket.getaddrinfo")
def test_timeout_raises_400(mock_getaddrinfo):
    mock_getaddrinfo.side_effect = socket.timeout("dns timeout")
    with pytest.raises(HTTPException) as exc:
        validate_url("http://nope.invalid/x")
    assert exc.value.status_code == 400


@patch("socket.getaddrinfo")
def test_generic_oserror_raises_400(mock_getaddrinfo):
    mock_getaddrinfo.side_effect = OSError("dns broken")
    with pytest.raises(HTTPException) as exc:
        validate_url("http://nope.invalid/x")
    assert exc.value.status_code == 400


@patch("socket.getaddrinfo")
def test_empty_resolution_raises_400(mock_getaddrinfo):
    """Defensive: an empty list previously fell through to `return True`."""
    mock_getaddrinfo.return_value = []
    with pytest.raises(HTTPException) as exc:
        validate_url("http://example.test/x")
    assert exc.value.status_code == 400
    assert "did not resolve" in exc.value.detail


@patch("socket.getaddrinfo")
def test_private_resolution_still_blocked(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [(2, 1, 6, "", ("10.0.0.5", 80))]
    with pytest.raises(HTTPException) as exc:
        validate_url("http://example.test/x")
    assert exc.value.status_code == 400
    assert "private IP" in exc.value.detail


@patch("socket.getaddrinfo")
def test_public_resolution_accepted(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 80))]
    assert validate_url("http://example.com/x") is True


def test_non_http_scheme_blocked():
    with pytest.raises(HTTPException) as exc:
        validate_url("file:///etc/passwd")
    assert exc.value.status_code == 400


def test_missing_hostname_blocked():
    # urlparse extracts an empty hostname from this.
    with pytest.raises(HTTPException) as exc:
        validate_url("http:///path")
    assert exc.value.status_code == 400
