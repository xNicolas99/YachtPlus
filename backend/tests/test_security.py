import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch
from fastapi import Request, HTTPException, status
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlalchemy import select, func

from api.db.database import Base
from api.utils.security import (
    is_private_ip,
    send_security_alert,
    check_ip_restriction,
    record_login_attempt,
)
from api.db.models.settings import SMTPSettings
from api.db.models.users import LoginAttempt, User


engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
TestingSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autocommit=False, autoflush=False)


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSessionLocal() as session:
        yield session


def test_is_private_ip():
    assert is_private_ip("127.0.0.1") is True
    assert is_private_ip("192.168.1.1") is True
    assert is_private_ip("10.0.0.1") is True
    assert is_private_ip("172.16.0.1") is True

    assert is_private_ip("8.8.8.8") is False
    assert is_private_ip("1.1.1.1") is False

    assert is_private_ip("invalid_ip") is False
    assert is_private_ip("256.256.256.256") is False


@pytest.mark.asyncio
async def test_send_security_alert_with_admin_user(db):
    settings = SMTPSettings(
        sender_email="alerts@example.com",
        server="smtp.example.com",
        port=587,
        use_tls=True,
        username="user",
        password="pass",
    )
    admin = User(username="admin@example.com", hashed_password="pw", is_superuser=True)
    db.add(settings)
    db.add(admin)
    await db.commit()

    with patch("api.utils.security.smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server

        await send_security_alert(db, "1.2.3.4", "Test Reason", "testuser")

    mock_smtp.assert_called_once_with("smtp.example.com", 587)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("user", "pass")
    mock_server.sendmail.assert_called_once()
    mock_server.quit.assert_called_once()

    call_args = mock_server.sendmail.call_args[0]
    assert call_args[0] == "alerts@example.com"
    assert call_args[1] == "alerts@example.com"
    assert "Security Alert: Test Reason" in call_args[2]
    assert "1.2.3.4" in call_args[2]
    assert "testuser" in call_args[2]


@pytest.mark.asyncio
async def test_send_security_alert_no_tls_no_auth(db):
    settings = SMTPSettings(
        sender_email="alerts@example.com",
        server="smtp.example.com",
        port=25,
        use_tls=False,
        username=None,
        password=None,
    )
    db.add(settings)
    await db.commit()

    with patch("api.utils.security.smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server

        await send_security_alert(db, "1.2.3.4", "Test Reason")

    mock_smtp.assert_called_once_with("smtp.example.com", 25)
    mock_server.starttls.assert_not_called()
    mock_server.login.assert_not_called()
    mock_server.sendmail.assert_called_once()
    mock_server.quit.assert_called_once()

    call_args = mock_server.sendmail.call_args[0]
    assert call_args[0] == "alerts@example.com"
    assert call_args[1] == "alerts@example.com"  # Fallback to sender_email


@pytest.mark.asyncio
async def test_send_security_alert_no_settings(db, caplog):
    with caplog.at_level("WARNING", logger="api.utils.security"):
        await send_security_alert(db, "1.2.3.4", "Test Reason")

    assert "SMTP settings not found" in caplog.text


@pytest.mark.asyncio
async def test_check_ip_restriction_private_ip(db):
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {}
    mock_request.client.host = "192.168.1.5"

    result = await check_ip_restriction(mock_request, db)
    assert result == "192.168.1.5"


@pytest.mark.asyncio
async def test_check_ip_restriction_public_ip(db):
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {}
    mock_request.client.host = "8.8.8.8"

    with pytest.raises(HTTPException) as exc_info:
        await check_ip_restriction(mock_request, db, "testuser")

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "Access denied from public IP" in exc_info.value.detail


@pytest.mark.asyncio
async def test_check_ip_restriction_fail2ban(db):
    # Seed 5 failed attempts for the private IP.
    for _ in range(5):
        db.add(LoginAttempt(ip_address="192.168.1.5", username="x", success=False))
    await db.commit()

    mock_request = MagicMock(spec=Request)
    mock_request.headers = {}
    mock_request.client.host = "192.168.1.5"

    with pytest.raises(HTTPException) as exc_info:
        await check_ip_restriction(mock_request, db, "testuser")

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "IP blocked due to too many failed login attempts" in exc_info.value.detail


@pytest.mark.asyncio
async def test_record_login_attempt(db):
    await record_login_attempt(db, "192.168.1.5", "testuser", False)

    result = await db.execute(select(LoginAttempt).filter(LoginAttempt.ip_address == "192.168.1.5"))
    attempt = result.scalars().first()
    assert attempt is not None
    assert attempt.username == "testuser"
    assert attempt.success is False
