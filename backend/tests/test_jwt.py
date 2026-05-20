from unittest.mock import MagicMock
from fastapi import Request
from api.auth.jwt import get_current_user_token

def test_get_current_user_token_header():
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {"Authorization": "Bearer test_token"}
    mock_request.cookies = {}
    assert get_current_user_token(mock_request) == "test_token"

def test_get_current_user_token_cookie():
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {}
    mock_request.cookies = {"access_token_cookie": "test_cookie_token"}
    assert get_current_user_token(mock_request) == "test_cookie_token"

def test_get_current_user_token_header_precedence():
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {"Authorization": "Bearer test_token"}
    mock_request.cookies = {"access_token_cookie": "test_cookie_token"}
    assert get_current_user_token(mock_request) == "test_token"

def test_get_current_user_token_invalid_header():
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {"Authorization": "Invalid test_token"}
    mock_request.cookies = {}
    assert get_current_user_token(mock_request) is None

def test_get_current_user_token_missing():
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {}
    mock_request.cookies = {}
    assert get_current_user_token(mock_request) is None
