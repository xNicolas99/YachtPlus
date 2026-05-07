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
def test_validate_url_valid(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [
        (2, 1, 6, '', ('93.184.216.34', 80))
    ]
    assert validate_url("http://example.com") is True
