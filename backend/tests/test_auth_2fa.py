import pytest
import pytest_asyncio
from fastapi import HTTPException
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlalchemy import select
import pyotp

from api.routers.auth_2fa import (
    generate_2fa_logic,
    generate_2fa_get,
    generate_2fa,
    enable_2fa,
    disable_2fa,
    TwoFactorRequest,
    Disable2FARequest,
)
from api.db.database import Base
from api.db.models.users import User
from api.db.crud.users import get_password_hash
from api.utils.crypto import encrypt, decrypt


engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


class MockAuth:
    def __init__(self, username, setup_pending=False):
        self.username = username

    async def jwt_required(self, allow_setup_pending=False):
        return True

    async def get_jwt_subject(self, allow_setup_pending=False):
        return self.username


@pytest.fixture(autouse=True)
def _force_auth_on(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", False)


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        yield s


async def _add_user(db, username, **kw):
    defaults = dict(hashed_password="pw", is_active=True, is_superuser=False)
    defaults.update(kw)
    u = User(username=username, **defaults)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _get_user(db, username):
    result = await db.execute(select(User).filter(User.username == username))
    return result.scalars().first()


# --- generate_2fa_logic (DB-backed) ---------------------------------------

@pytest.mark.asyncio
async def test_generate_2fa_logic_success(db):
    await _add_user(db, "logic_user")
    auth = MockAuth("logic_user")
    result = await generate_2fa_logic(db, auth)

    assert "secret" in result
    assert "qr_code" in result
    assert "provisioning_uri" in result
    assert result["qr_code"].startswith("data:image/png;base64,")

    user = await _get_user(db, "logic_user")
    assert user.otp_secret is not None
    assert decrypt(user.otp_secret) == result["secret"]


@pytest.mark.asyncio
async def test_generate_2fa_logic_user_not_found(db):
    auth = MockAuth("ghost")
    with pytest.raises(HTTPException) as excinfo:
        await generate_2fa_logic(db, auth)
    assert excinfo.value.status_code == 404
    assert "User not found" in excinfo.value.detail


# --- Router wrappers --------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_2fa_get():
    mock_db = MagicMock()
    mock_auth = AsyncMock()
    with patch("api.routers.auth_2fa.generate_2fa_logic", return_value={"status": "ok"}) as mock_logic:
        result = await generate_2fa_get(mock_db, mock_auth)
    assert result == {"status": "ok"}
    mock_logic.assert_awaited_once_with(mock_db, mock_auth)


@pytest.mark.asyncio
async def test_generate_2fa_post():
    mock_db = MagicMock()
    mock_auth = AsyncMock()
    with patch("api.routers.auth_2fa.generate_2fa_logic", return_value={"status": "ok"}) as mock_logic:
        result = await generate_2fa(mock_db, mock_auth)
    assert result == {"status": "ok"}
    mock_logic.assert_awaited_once_with(mock_db, mock_auth)


# --- enable_2fa -------------------------------------------------------------

@pytest.mark.asyncio
async def test_enable_2fa_user_not_found(db):
    auth = MockAuth("ghost")
    payload = TwoFactorRequest(code="123456")
    with pytest.raises(HTTPException) as exc:
        await enable_2fa(payload=payload, db=db, Authorize=auth)
    assert exc.value.status_code == 400
    assert exc.value.detail == "2FA setup not initiated"


@pytest.mark.asyncio
async def test_enable_2fa_success(db):
    secret = pyotp.random_base32()
    await _add_user(db, "alice", otp_secret=encrypt(secret))
    auth = MockAuth("alice")
    payload = TwoFactorRequest(code=pyotp.TOTP(secret).now())
    result = await enable_2fa(payload=payload, db=db, Authorize=auth)
    assert result == {"message": "2FA enabled successfully"}
    user = await _get_user(db, "alice")
    assert user.is_2fa_enabled is True


@pytest.mark.asyncio
async def test_enable_2fa_invalid_code(db):
    secret = pyotp.random_base32()
    await _add_user(db, "alice", otp_secret=encrypt(secret))
    auth = MockAuth("alice")
    payload = TwoFactorRequest(code="000000")
    with pytest.raises(HTTPException) as exc:
        await enable_2fa(payload=payload, db=db, Authorize=auth)
    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid token or secret error"


# --- disable_2fa ------------------------------------------------------------

@pytest.mark.asyncio
async def test_disable_2fa_success(db):
    secret = pyotp.random_base32()
    await _add_user(
        db,
        "alice",
        hashed_password=await get_password_hash("pw"),
        is_2fa_enabled=True,
        otp_secret=encrypt(secret),
    )
    auth = MockAuth("alice")
    payload = Disable2FARequest(password="pw", code=pyotp.TOTP(secret).now())
    result = await disable_2fa(payload=payload, db=db, Authorize=auth)
    assert result == {"message": "2FA disabled successfully"}
    user = await _get_user(db, "alice")
    assert user.is_2fa_enabled is False
    assert user.otp_secret is None


@pytest.mark.asyncio
async def test_disable_2fa_user_not_found(db):
    auth = MockAuth("ghost")
    payload = Disable2FARequest(password="pw")
    with pytest.raises(HTTPException) as exc:
        await disable_2fa(payload=payload, db=db, Authorize=auth)
    assert exc.value.status_code == 404
