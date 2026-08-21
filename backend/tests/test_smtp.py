import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlalchemy import select, func

from api.db.database import Base
from api.db.models.settings import SMTPSettings
from api.db.models.users import User
from api.routers.smtp import (
    SMTPSettingsSchema,
    TestEmailSchema as _TestEmailSchema,
    get_smtp_settings,
    update_smtp_settings,
    send_test_email,
    get_db,
)

EmailPayload = _TestEmailSchema

engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autocommit=False, autoflush=False)


class MockAuthValid:
    async def jwt_required(self, allow_setup_pending=False):
        return True

    async def get_jwt_subject(self, allow_setup_pending=False):
        return "admin"


class MockAuthInvalid:
    async def jwt_required(self, allow_setup_pending=False):
        raise HTTPException(status_code=401, detail="Unauthorized")

    async def get_jwt_subject(self, allow_setup_pending=False):
        raise HTTPException(status_code=401, detail="Unauthorized")


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        session.add(User(username="admin", hashed_password="pw", is_superuser=True))
        await session.commit()
        yield session


@pytest.fixture
def mock_settings_auth_enabled(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


@pytest.fixture(autouse=True)
def _reset_smtp_debounce():
    import api.routers.smtp as smtp_mod
    smtp_mod._test_mail_last_sent = 0.0


@pytest.mark.asyncio
async def test_get_db_dependency_yields_and_closes():
    db_gen = get_db()
    session = await db_gen.asend(None)
    assert isinstance(session, AsyncSession)
    with pytest.raises(StopAsyncIteration):
        await db_gen.asend(None)


@pytest.mark.asyncio
async def test_get_smtp_settings_returns_defaults_when_empty(db, mock_settings_auth_enabled):
    auth = MockAuthValid()
    result = await get_smtp_settings(db=db, Authorize=auth)
    assert result.server == ""
    assert result.port == 587
    assert result.sender_email == "admin@example.com"


@pytest.mark.asyncio
async def test_get_smtp_settings_returns_stored(db, mock_settings_auth_enabled):
    db.add(SMTPSettings(
        server="smtp.example.com",
        port=465,
        username="user",
        password="pw",
        sender_email="from@example.com",
        use_tls=False,
    ))
    await db.commit()
    auth = MockAuthValid()
    result = await get_smtp_settings(db=db, Authorize=auth)
    assert result.server == "smtp.example.com"
    assert result.port == 465
    assert result.username == "user"
    assert result.sender_email == "from@example.com"
    assert result.use_tls is False


@pytest.mark.asyncio
async def test_get_smtp_settings_unauthorized(db, mock_settings_auth_enabled):
    auth = MockAuthInvalid()
    with pytest.raises(HTTPException) as exc:
        await get_smtp_settings(db=db, Authorize=auth)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_update_smtp_settings_creates_new(db, mock_settings_auth_enabled):
    payload = SMTPSettingsSchema(
        server="smtp.new.com",
        port=587,
        username="u",
        password="p",
        sender_email="me@new.com",
        use_tls=True,
    )
    auth = MockAuthValid()
    result = await update_smtp_settings(payload, db=db, Authorize=auth)
    assert result.server == "smtp.new.com"
    count_result = await db.execute(select(func.count()).select_from(SMTPSettings))
    assert count_result.scalar() == 1


@pytest.mark.asyncio
async def test_update_smtp_settings_updates_existing(db, mock_settings_auth_enabled):
    db.add(SMTPSettings(
        server="old.com", port=25, sender_email="old@old.com", use_tls=False
    ))
    await db.commit()
    payload = SMTPSettingsSchema(
        server="new.com",
        port=465,
        sender_email="new@new.com",
        use_tls=True,
    )
    auth = MockAuthValid()
    result = await update_smtp_settings(payload, db=db, Authorize=auth)
    assert result.server == "new.com"
    assert result.port == 465
    assert result.use_tls is True
    count_result = await db.execute(select(func.count()).select_from(SMTPSettings))
    assert count_result.scalar() == 1


@pytest.mark.asyncio
async def test_update_smtp_settings_unauthorized(db, mock_settings_auth_enabled):
    auth = MockAuthInvalid()
    payload = SMTPSettingsSchema(
        server="x", port=1, sender_email="a@b.com", use_tls=True
    )
    with pytest.raises(HTTPException) as exc:
        await update_smtp_settings(payload, db=db, Authorize=auth)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_send_test_email_no_settings_raises_400(db, mock_settings_auth_enabled):
    auth = MockAuthValid()
    email_data = EmailPayload(recipient="to@example.com")
    with pytest.raises(HTTPException) as exc:
        await send_test_email(None, email_data, db=db, Authorize=auth)
    assert exc.value.status_code == 400
    assert "SMTP settings not configured" in exc.value.detail


@pytest.mark.asyncio
async def test_send_test_email_with_tls_and_credentials(db, mock_settings_auth_enabled):
    db.add(SMTPSettings(
        server="smtp.example.com",
        port=587,
        username="u",
        password="p",
        sender_email="from@example.com",
        use_tls=True,
    ))
    await db.commit()

    auth = MockAuthValid()
    email_data = EmailPayload(recipient="to@example.com")

    with patch("api.routers.smtp.smtplib.SMTP") as smtp_cls:
        server = MagicMock()
        smtp_cls.return_value = server

        result = await send_test_email(None, email_data, db=db, Authorize=auth)

    smtp_cls.assert_called_once_with("smtp.example.com", 587)
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("u", "p")
    server.sendmail.assert_called_once()
    args, _ = server.sendmail.call_args
    assert args[0] == "from@example.com"
    assert args[1] == "to@example.com"
    server.quit.assert_called_once()
    assert result == {"message": "Test email sent successfully"}


@pytest.mark.asyncio
async def test_send_test_email_without_tls_or_credentials(db, mock_settings_auth_enabled):
    db.add(SMTPSettings(
        server="smtp.example.com",
        port=25,
        username=None,
        password=None,
        sender_email="from@example.com",
        use_tls=False,
    ))
    await db.commit()

    auth = MockAuthValid()
    email_data = EmailPayload(recipient="to@example.com")

    with patch("api.routers.smtp.smtplib.SMTP") as smtp_cls:
        server = MagicMock()
        smtp_cls.return_value = server

        await send_test_email(None, email_data, db=db, Authorize=auth)

    server.starttls.assert_not_called()
    server.login.assert_not_called()
    server.sendmail.assert_called_once()
    server.quit.assert_called_once()


@pytest.mark.asyncio
async def test_send_test_email_smtp_failure_returns_500(db, mock_settings_auth_enabled):
    db.add(SMTPSettings(
        server="smtp.example.com",
        port=587,
        sender_email="from@example.com",
        use_tls=True,
    ))
    await db.commit()

    auth = MockAuthValid()
    email_data = EmailPayload(recipient="to@example.com")

    with patch("api.routers.smtp.smtplib.SMTP", side_effect=OSError("connection refused")):
        with pytest.raises(HTTPException) as exc:
            await send_test_email(None, email_data, db=db, Authorize=auth)

    assert exc.value.status_code == 500
    assert "SMTP test failed" in exc.value.detail


@pytest.mark.asyncio
async def test_send_test_email_unauthorized(db, mock_settings_auth_enabled):
    auth = MockAuthInvalid()
    email_data = EmailPayload(recipient="to@example.com")
    with pytest.raises(HTTPException) as exc:
        await send_test_email(None, email_data, db=db, Authorize=auth)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_send_test_email_requires_request_param_and_rate_limit():
    import inspect
    from api.routers import smtp as smtp_mod

    sig = inspect.signature(smtp_mod.send_test_email)
    assert "request" in sig.parameters, "send_test_email must accept request for rate limiting"
    # The endpoint should be wrapped by slowapi limiter (function name changes to wrapper).
    # At minimum, the underlying function is still importable and the module has a limiter import.
    assert hasattr(smtp_mod, "limiter")
    assert smtp_mod._TEST_MAIL_COOLDOWN_SECONDS >= 10
