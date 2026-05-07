import pytest
from unittest.mock import MagicMock, patch
from fastapi import Request, HTTPException, status

from api.utils.security import (
    is_private_ip,
    send_security_alert,
    check_ip_restriction,
    record_login_attempt
)
from api.db.models.settings import SMTPSettings
from api.db.models.users import LoginAttempt, User

def test_is_private_ip():
    assert is_private_ip("127.0.0.1") is True
    assert is_private_ip("192.168.1.1") is True
    assert is_private_ip("10.0.0.1") is True
    assert is_private_ip("172.16.0.1") is True

    assert is_private_ip("8.8.8.8") is False
    assert is_private_ip("1.1.1.1") is False

    assert is_private_ip("invalid_ip") is False
    assert is_private_ip("256.256.256.256") is False

@patch("api.utils.security.smtplib.SMTP")
def test_send_security_alert_with_admin_user(mock_smtp):
    mock_db = MagicMock()
    mock_settings = MagicMock(spec=SMTPSettings)
    mock_settings.sender_email = "alerts@example.com"
    mock_settings.server = "smtp.example.com"
    mock_settings.port = 587
    mock_settings.use_tls = True
    mock_settings.username = "user"
    mock_settings.password = "pass"

    mock_admin = MagicMock(spec=User)
    mock_admin.username = "admin@example.com"

    # Mocking db.query chaining logic.
    # db.query(SMTPSettings).first() returns mock_settings
    # db.query(User).filter(...).first() returns None for first call, mock_admin for second
    mock_smtp_query = MagicMock()
    mock_smtp_query.first.return_value = mock_settings

    mock_user_query = MagicMock()
    # The first filter call is for sender_email, the second is for is_superuser
    mock_user_query.filter.return_value.first.side_effect = [None, mock_admin]

    def db_query_side_effect(model):
        if model == SMTPSettings:
            return mock_smtp_query
        elif model == User:
            return mock_user_query
        return MagicMock()

    mock_db.query.side_effect = db_query_side_effect

    mock_server = MagicMock()
    mock_smtp.return_value = mock_server

    send_security_alert(mock_db, "1.2.3.4", "Test Reason", "testuser")

    mock_smtp.assert_called_once_with("smtp.example.com", 587)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("user", "pass")
    mock_server.sendmail.assert_called_once()
    mock_server.quit.assert_called_once()

    call_args = mock_server.sendmail.call_args[0]
    assert call_args[0] == "alerts@example.com"
    assert call_args[1] == "admin@example.com"
    assert "Security Alert: Test Reason" in call_args[2]
    assert "1.2.3.4" in call_args[2]
    assert "testuser" in call_args[2]

@patch("api.utils.security.smtplib.SMTP")
def test_send_security_alert_no_tls_no_auth(mock_smtp):
    mock_db = MagicMock()
    mock_settings = MagicMock(spec=SMTPSettings)
    mock_settings.sender_email = "alerts@example.com"
    mock_settings.server = "smtp.example.com"
    mock_settings.port = 25
    mock_settings.use_tls = False
    mock_settings.username = None
    mock_settings.password = None

    def db_query_side_effect(model):
        query_mock = MagicMock()
        if model == SMTPSettings:
            query_mock.first.return_value = mock_settings
        elif model == User:
            query_mock.filter.return_value.first.return_value = None
        return query_mock

    mock_db.query.side_effect = db_query_side_effect

    mock_server = MagicMock()
    mock_smtp.return_value = mock_server

    send_security_alert(mock_db, "1.2.3.4", "Test Reason")

    mock_smtp.assert_called_once_with("smtp.example.com", 25)
    mock_server.starttls.assert_not_called()
    mock_server.login.assert_not_called()
    mock_server.sendmail.assert_called_once()
    mock_server.quit.assert_called_once()

    call_args = mock_server.sendmail.call_args[0]
    assert call_args[0] == "alerts@example.com"
    assert call_args[1] == "alerts@example.com" # Fallback to sender_email

@patch("builtins.print")
def test_send_security_alert_no_settings(mock_print):
    mock_db = MagicMock()
    mock_db.query.return_value.first.return_value = None

    send_security_alert(mock_db, "1.2.3.4", "Test Reason")

    mock_print.assert_called_once_with("SMTP Settings not found, cannot send alert.")

def test_check_ip_restriction_private_ip():
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {}
    mock_request.client.host = "192.168.1.5"

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.count.return_value = 0

    result = check_ip_restriction(mock_request, mock_db)
    assert result == "192.168.1.5"

def test_check_ip_restriction_x_forwarded_for_private():
    mock_request = MagicMock(spec=Request)
    # Safe fallback parsing of X-Forwarded-For: traversing from right to left
    # Here all are private, so we'll fallback to the leftmost
    mock_request.headers = {"X-Forwarded-For": "10.0.0.5, 10.0.0.6"}
    mock_request.client.host = "127.0.0.1"

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.count.return_value = 0

    result = check_ip_restriction(mock_request, mock_db)
    assert result == "10.0.0.5"

def test_check_ip_restriction_x_real_ip_private():
    mock_request = MagicMock(spec=Request)
    # X-Real-IP should take precedence when client host is private (from nginx)
    mock_request.headers = {"X-Real-IP": "10.0.0.6", "X-Forwarded-For": "1.2.3.4"}
    mock_request.client.host = "127.0.0.1"

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.count.return_value = 0

    result = check_ip_restriction(mock_request, mock_db)
    assert result == "10.0.0.6"

def test_check_ip_restriction_x_real_ip_ignored_if_host_public():
    mock_request = MagicMock(spec=Request)
    # X-Real-IP is ignored if the immediate client is not a private IP
    mock_request.headers = {"X-Real-IP": "10.0.0.6"}
    mock_request.client.host = "8.8.8.8"

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.count.return_value = 0
    mock_db.query.return_value.first.return_value = MagicMock(sender_email="test@test.com")

    # Should raise 403 because 8.8.8.8 is used
    with pytest.raises(HTTPException) as excinfo:
        check_ip_restriction(mock_request, mock_db)

    assert excinfo.value.status_code == 403

def test_check_ip_restriction_x_forwarded_for_public():
    mock_request = MagicMock(spec=Request)
    # Testing that the rightmost public IP is picked if spoofed:
    # Client sends 'X-Forwarded-For: 127.0.0.1', proxy appends '8.8.8.8' -> '127.0.0.1, 8.8.8.8'
    mock_request.headers = {"X-Forwarded-For": "127.0.0.1, 8.8.8.8"}
    mock_request.client.host = "127.0.0.1"

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.count.return_value = 0
    mock_db.query.return_value.first.return_value = MagicMock(sender_email="test@test.com")

    with pytest.raises(HTTPException) as excinfo:
        check_ip_restriction(mock_request, mock_db)

    assert excinfo.value.status_code == 403

@patch("api.utils.security.send_security_alert")
def test_check_ip_restriction_public_ip(mock_alert):
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {}
    mock_request.client.host = "8.8.8.8"

    mock_db = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        check_ip_restriction(mock_request, mock_db, "testuser")

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "Access denied from public IP" in exc_info.value.detail

    mock_alert.assert_called_once_with(mock_db, "8.8.8.8", "Non-Private IP Login Attempt Blocked", "testuser")

@patch("api.utils.security.send_security_alert")
def test_check_ip_restriction_fail2ban(mock_alert):
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {}
    mock_request.client.host = "192.168.1.5"

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.count.return_value = 5

    with pytest.raises(HTTPException) as exc_info:
        check_ip_restriction(mock_request, mock_db, "testuser")

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "IP blocked due to too many failed login attempts" in exc_info.value.detail

    mock_alert.assert_called_once_with(mock_db, "192.168.1.5", "Too many failed login attempts (Fail2Ban)", "testuser")

@patch("api.utils.security.LoginAttempt")
def test_record_login_attempt(mock_login_attempt):
    mock_db = MagicMock()
    mock_attempt_instance = MagicMock()
    mock_login_attempt.return_value = mock_attempt_instance

    record_login_attempt(mock_db, "192.168.1.5", "testuser", False)

    mock_login_attempt.assert_called_once_with(ip_address="192.168.1.5", username="testuser", success=False)
    mock_db.add.assert_called_once_with(mock_attempt_instance)
    mock_db.commit.assert_called_once()
