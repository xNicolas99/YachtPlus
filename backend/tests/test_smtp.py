import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from api.db.database import Base
from api.db.models.settings import SMTPSettings
from api.routers.smtp import (
    SMTPSettingsSchema,
    TestEmailSchema as _TestEmailSchema,
    get_smtp_settings,
    update_smtp_settings,
    send_test_email,
    get_db,
)

# Aliased to avoid pytest treating it as a test class (it has a non-pytest __init__).
EmailPayload = _TestEmailSchema

engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


class MockAuthValid:
    def jwt_required(self, allow_setup_pending=False):
        return True

    def get_jwt_subject(self, allow_setup_pending=False):
        return "admin"


class MockAuthInvalid:
    def jwt_required(self, allow_setup_pending=False):
        raise HTTPException(status_code=401, detail="Unauthorized")


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def mock_settings_auth_enabled(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


def test_get_db_dependency_yields_and_closes():
    db_gen = get_db()
    session = next(db_gen)
    assert isinstance(session, Session)
    with pytest.raises(StopIteration):
        next(db_gen)


def test_get_smtp_settings_returns_defaults_when_empty(db, mock_settings_auth_enabled):
    auth = MockAuthValid()
    result = get_smtp_settings(db=db, Authorize=auth)
    assert result.server == ""
    assert result.port == 587
    assert result.sender_email == "admin@example.com"


def test_get_smtp_settings_returns_stored(db, mock_settings_auth_enabled):
    db.add(SMTPSettings(
        server="smtp.example.com",
        port=465,
        username="user",
        password="pw",
        sender_email="from@example.com",
        use_tls=False,
    ))
    db.commit()
    auth = MockAuthValid()
    result = get_smtp_settings(db=db, Authorize=auth)
    assert result.server == "smtp.example.com"
    assert result.port == 465
    assert result.username == "user"
    assert result.sender_email == "from@example.com"
    assert result.use_tls is False


def test_get_smtp_settings_unauthorized(db, mock_settings_auth_enabled):
    auth = MockAuthInvalid()
    with pytest.raises(HTTPException) as exc:
        get_smtp_settings(db=db, Authorize=auth)
    assert exc.value.status_code == 401


def test_update_smtp_settings_creates_new(db, mock_settings_auth_enabled):
    payload = SMTPSettingsSchema(
        server="smtp.new.com",
        port=587,
        username="u",
        password="p",
        sender_email="me@new.com",
        use_tls=True,
    )
    auth = MockAuthValid()
    result = update_smtp_settings(payload, db=db, Authorize=auth)
    assert result.server == "smtp.new.com"
    assert db.query(SMTPSettings).count() == 1


def test_update_smtp_settings_updates_existing(db, mock_settings_auth_enabled):
    db.add(SMTPSettings(
        server="old.com", port=25, sender_email="old@old.com", use_tls=False
    ))
    db.commit()
    payload = SMTPSettingsSchema(
        server="new.com",
        port=465,
        sender_email="new@new.com",
        use_tls=True,
    )
    auth = MockAuthValid()
    result = update_smtp_settings(payload, db=db, Authorize=auth)
    assert result.server == "new.com"
    assert result.port == 465
    assert result.use_tls is True
    assert db.query(SMTPSettings).count() == 1


def test_update_smtp_settings_unauthorized(db, mock_settings_auth_enabled):
    auth = MockAuthInvalid()
    payload = SMTPSettingsSchema(
        server="x", port=1, sender_email="a@b.com", use_tls=True
    )
    with pytest.raises(HTTPException) as exc:
        update_smtp_settings(payload, db=db, Authorize=auth)
    assert exc.value.status_code == 401


def test_send_test_email_no_settings_raises_400(db, mock_settings_auth_enabled):
    auth = MockAuthValid()
    payload = EmailPayload(recipient="to@example.com")
    with pytest.raises(HTTPException) as exc:
        send_test_email(payload, db=db, Authorize=auth)
    assert exc.value.status_code == 400
    assert "SMTP settings not configured" in exc.value.detail


def test_send_test_email_with_tls_and_credentials(db, mock_settings_auth_enabled):
    db.add(SMTPSettings(
        server="smtp.example.com",
        port=587,
        username="u",
        password="p",
        sender_email="from@example.com",
        use_tls=True,
    ))
    db.commit()

    auth = MockAuthValid()
    payload = EmailPayload(recipient="to@example.com")

    with patch("api.routers.smtp.smtplib.SMTP") as smtp_cls:
        server = MagicMock()
        smtp_cls.return_value = server

        result = send_test_email(payload, db=db, Authorize=auth)

    smtp_cls.assert_called_once_with("smtp.example.com", 587)
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("u", "p")
    server.sendmail.assert_called_once()
    args, _ = server.sendmail.call_args
    assert args[0] == "from@example.com"
    assert args[1] == "to@example.com"
    server.quit.assert_called_once()
    assert result == {"message": "Test email sent successfully"}


def test_send_test_email_without_tls_or_credentials(db, mock_settings_auth_enabled):
    db.add(SMTPSettings(
        server="smtp.example.com",
        port=25,
        username=None,
        password=None,
        sender_email="from@example.com",
        use_tls=False,
    ))
    db.commit()

    auth = MockAuthValid()
    payload = EmailPayload(recipient="to@example.com")

    with patch("api.routers.smtp.smtplib.SMTP") as smtp_cls:
        server = MagicMock()
        smtp_cls.return_value = server

        send_test_email(payload, db=db, Authorize=auth)

    server.starttls.assert_not_called()
    server.login.assert_not_called()
    server.sendmail.assert_called_once()
    server.quit.assert_called_once()


def test_send_test_email_smtp_failure_returns_500(db, mock_settings_auth_enabled):
    db.add(SMTPSettings(
        server="smtp.example.com",
        port=587,
        sender_email="from@example.com",
        use_tls=True,
    ))
    db.commit()

    auth = MockAuthValid()
    payload = EmailPayload(recipient="to@example.com")

    with patch("api.routers.smtp.smtplib.SMTP", side_effect=OSError("connection refused")):
        with pytest.raises(HTTPException) as exc:
            send_test_email(payload, db=db, Authorize=auth)

    assert exc.value.status_code == 500
    assert "connection refused" in exc.value.detail


def test_send_test_email_unauthorized(db, mock_settings_auth_enabled):
    auth = MockAuthInvalid()
    payload = EmailPayload(recipient="to@example.com")
    with pytest.raises(HTTPException) as exc:
        send_test_email(payload, db=db, Authorize=auth)
    assert exc.value.status_code == 401
