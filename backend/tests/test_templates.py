import pytest
from fastapi import HTTPException
from unittest.mock import patch
from api.db.crud.templates import validate_url

def test_validate_url_malformed():
    with pytest.raises(HTTPException) as exc_info:
        validate_url("http:///")
    assert exc_info.value.status_code == 400
    assert "Hostname missing" in exc_info.value.detail

def test_validate_url_missing_scheme():
    with pytest.raises(HTTPException) as exc_info:
        validate_url("example.com")
    assert exc_info.value.status_code == 400
    assert "Invalid URL scheme" in exc_info.value.detail

def test_validate_url_invalid_scheme():
    with pytest.raises(HTTPException) as exc_info:
        validate_url("ftp://example.com")
    assert exc_info.value.status_code == 400
    assert "Invalid URL scheme" in exc_info.value.detail

@patch('socket.getaddrinfo')
def test_validate_url_private_ip(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [
        (2, 1, 6, '', ('127.0.0.1', 80))
    ]
    with pytest.raises(HTTPException) as exc_info:
        validate_url("http://localhost")
    assert exc_info.value.status_code == 400
    assert "Access to private IP 127.0.0.1 is denied." in exc_info.value.detail

@patch('socket.getaddrinfo')
def test_validate_url_private_ip_multiple(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [
        (2, 1, 6, '', ('93.184.216.34', 80)),
        (2, 1, 6, '', ('192.168.1.1', 80))
    ]
    with pytest.raises(HTTPException) as exc_info:
        validate_url("http://example.com")
    assert exc_info.value.status_code == 400
    assert "Access to private IP 192.168.1.1 is denied." in exc_info.value.detail

@patch('socket.getaddrinfo')
def test_validate_url_valid(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [
        (2, 1, 6, '', ('93.184.216.34', 80))
    ]
    assert validate_url("http://example.com") is True

@patch('socket.getaddrinfo')
def test_validate_url_valid_multiple(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [
        (2, 1, 6, '', ('93.184.216.34', 80)),
        (2, 1, 6, '', ('93.184.216.35', 80))
    ]
    assert validate_url("http://example.com") is True

@patch('socket.getaddrinfo')
def test_validate_url_socket_error(mock_getaddrinfo):
    import socket
    mock_getaddrinfo.side_effect = socket.gaierror
    # socket.gaierror should be caught and passed through
    assert validate_url("http://unresolvable.example.com") is True

@patch('socket.getaddrinfo')
def test_validate_url_zero_ip(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [
        (2, 1, 6, '', ('0.0.0.0', 80))
    ]
    with pytest.raises(HTTPException) as exc_info:
        validate_url("http://0.0.0.0")
    assert exc_info.value.status_code == 400
    assert "Access to private IP 0.0.0.0 is denied." in exc_info.value.detail

def test_is_private_ip():
    from api.db.crud.templates import is_private_ip
    assert is_private_ip("0.0.0.0") is True
    assert is_private_ip("127.0.0.1") is True
    assert is_private_ip("192.168.1.1") is True
    assert is_private_ip("10.0.0.1") is True
    assert is_private_ip("172.16.0.1") is True
    assert is_private_ip("93.184.216.34") is False
    # Test invalid IPs (returns False)
    assert is_private_ip("not_an_ip") is False
