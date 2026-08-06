"""Regression for BUG-003: login's 2FA branch wrapped totp.verify() in
`except Exception` which ALSO caught the legitimate HTTPException(400)
raised on a bad code. That collapsed two distinct failure modes ("user
entered the wrong code" vs "decrypt of the stored secret threw") into
one ambiguous handler, hid the real exception type from the audit log,
and made the failure indistinguishable in production.

The fix separates the two: HTTPException re-raises unchanged, and only
the genuine decrypt/parse errors are funneled to the generic 400 path.
"""
import pyotp
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from api.db.database import Base
from api.db.models.users import User
from api.db.crud.users import get_password_hash, verify_password
from api.utils.crypto import encrypt
from api.routers.users import login, login_cookie, limiter as _users_limiter
from api.db.schemas.users import UserLogin


engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


class MockAuth:
    async def jwt_required(self, allow_setup_pending=False):
        return True

    async def get_jwt_subject(self, allow_setup_pending=False):
        return None

    def set_access_cookies(self, *a, **kw):
        pass


@pytest.fixture(autouse=True)
def _disable_users_limiter(monkeypatch):
    monkeypatch.setattr(_users_limiter, "enabled", False)


@pytest.fixture(autouse=True)
def _stub_security(monkeypatch):
    # The login flow consults check_ip_restriction / record_login_attempt
    # which want a real request/db combination; stub them so the tests
    # focus on the exception-handling branch.
    monkeypatch.setattr(
        "api.routers.users.check_ip_restriction", AsyncMock(return_value="127.0.0.1")
    )
    monkeypatch.setattr(
        "api.routers.users.record_login_attempt", AsyncMock(return_value=None)
    )


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        yield s


async def _seed_2fa_user(db, password="rightpw"):
    secret = pyotp.random_base32()
    user = User(
        username="alice",
        hashed_password=await get_password_hash(password),
        is_active=True,
        is_2fa_enabled=True,
        otp_secret=encrypt(secret),
    )
    db.add(user)
    await db.commit()
    return secret


@pytest.mark.asyncio
async def test_wrong_2fa_code_returns_400_without_swallowing_into_2fa_error(db):
    """A wrong code must surface as the "Invalid 2FA code" branch.
    Previously this code path was masked by the catch-all `except Exception`
    that converted it into a generic "2FA Error" log line — making it
    impossible to alert on real crypto corruption separately from users
    fat-fingering their code.
    """
    await _seed_2fa_user(db)
    request = MagicMock()
    payload = UserLogin(username="alice", password="rightpw", otp_token="000000")

    with patch("api.routers.users.logger") as mock_logger:
        with pytest.raises(HTTPException) as exc:
            await login(request=request, user_data=payload, db=db, Authorize=MockAuth())
    assert exc.value.status_code == 400
    # The "Invalid 2FA code" warning must fire — the "2FA Error" warning
    # must NOT (that path is now reserved for real exceptions).
    warning_messages = [
        c.args[0] for c in mock_logger.warning.call_args_list if c.args
    ]
    assert any("Invalid 2FA code" in m for m in warning_messages)
    assert not any("Reason: 2FA Error" in m for m in warning_messages)


@pytest.mark.asyncio
async def test_decrypt_failure_still_maps_to_generic_400(db):
    """If the stored OTP secret has been corrupted (key rotation, DB
    restore from a different env, etc.), decrypt() raises and we want
    the 400 path — but logged via the "2FA Error" branch, not the
    "Invalid 2FA code" one. This makes the two scenarios alertable
    separately in production.
    """
    await _seed_2fa_user(db)
    request = MagicMock()
    payload = UserLogin(username="alice", password="rightpw", otp_token="123456")

    with patch("api.routers.users.decrypt", side_effect=ValueError("bad key")), \
         patch("api.routers.users.logger") as mock_logger:
        with pytest.raises(HTTPException) as exc:
            await login(request=request, user_data=payload, db=db, Authorize=MockAuth())
    assert exc.value.status_code == 400
    warning_messages = [
        c.args[0] for c in mock_logger.warning.call_args_list if c.args
    ]
    assert any("Reason: 2FA Error" in m for m in warning_messages)
    assert not any("Invalid 2FA code" in m for m in warning_messages)


@pytest.mark.asyncio
async def test_correct_2fa_code_logs_in_successfully(db):
    """End-to-end happy path through the corrected branch."""
    secret = await _seed_2fa_user(db)
    request = MagicMock()
    payload = UserLogin(
        username="alice",
        password="rightpw",
        otp_token=pyotp.TOTP(secret).now(),
    )
    result = await login(request=request, user_data=payload, db=db, Authorize=MockAuth())
    assert result["login"] == "successful"
    assert result["username"] == "alice"


@pytest.mark.asyncio
async def test_login_cookie_same_separation(db):
    """login_cookie shared the bug; assert the matching fix is in place."""
    await _seed_2fa_user(db)
    request = MagicMock()
    response = MagicMock()
    payload = UserLogin(username="alice", password="rightpw", otp_token="000000")
    with pytest.raises(HTTPException) as exc:
        await login_cookie(
            request=request, response=response, user_data=payload,
            db=db, Authorize=MockAuth(),
        )
    assert exc.value.status_code == 400
