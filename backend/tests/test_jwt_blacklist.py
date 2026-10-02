"""Regression for BUG-010: /logout used to be a no-op for JWT auth —
the cookie was cleared, but the JWT itself remained valid until its
`exp` claim. Anyone who'd captured the token (XSS, leaked cookie jar,
session restore) could keep using it after the user logged out.

The fix:
  - every freshly minted token carries a unique `jti` claim,
  - logout decodes the active token and inserts its jti into the
    `jwt_token_blacklist` table,
  - verify_token() checks the blacklist on every call and rejects
    revoked tokens as if they were expired.
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlalchemy import select

from api.db.database import Base
from api.db.models.settings import TokenBlacklist
from api.auth.jwt import create_access_token, verify_token, revoke_token


engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def _shared_db(monkeypatch):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    # Patch the lazy-import target used by _is_jti_revoked / revoke_token.
    import api.db.database as db_mod
    monkeypatch.setattr(db_mod, "SessionLocal", SessionLocal)
    yield


def test_create_access_token_includes_jti():
    """The fix only works if every minted token carries a unique jti."""
    import jwt as _pyjwt
    from api.auth.jwt import get_secret_key

    t = create_access_token({"sub": "alice"})
    decoded = _pyjwt.decode(t, get_secret_key(), algorithms=["HS256"])
    assert decoded.get("jti")
    # Two consecutive mints must NOT share a jti.
    t2 = create_access_token({"sub": "alice"})
    decoded2 = _pyjwt.decode(t2, get_secret_key(), algorithms=["HS256"])
    assert decoded.get("jti") != decoded2.get("jti")


@pytest.mark.asyncio
async def test_token_verifies_before_revoke():
    from fastapi import HTTPException, status
    token = create_access_token({"sub": "alice"})
    exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="x")
    data = await verify_token(token, exc)
    assert data.username == "alice"


@pytest.mark.asyncio
async def test_token_rejected_after_revoke():
    from fastapi import HTTPException, status
    token = create_access_token({"sub": "alice"})
    await revoke_token(token)
    exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="x")
    with pytest.raises(HTTPException):
        await verify_token(token, exc)


@pytest.mark.asyncio
async def test_revoke_writes_blacklist_row():
    import jwt as _pyjwt
    from api.auth.jwt import get_secret_key

    token = create_access_token({"sub": "alice"})
    jti = _pyjwt.decode(token, get_secret_key(), algorithms=["HS256"])["jti"]

    await revoke_token(token)

    async with SessionLocal() as db:
        result = await db.execute(
            select(TokenBlacklist).filter(TokenBlacklist.jti == jti)
        )
        row = result.scalars().first()
        assert row is not None
        assert row.revoked is True


@pytest.mark.asyncio
async def test_revoke_idempotent():
    """Calling revoke twice on the same token must not error."""
    token = create_access_token({"sub": "alice"})
    await revoke_token(token)
    await revoke_token(token)  # no raise


@pytest.mark.asyncio
async def test_revoke_with_garbage_token_is_safe():
    """Malformed or unsigned tokens passed to revoke_token (e.g. a forged
    or truncated cookie value) must not raise — we just want to clear
    the session, never spam 500s."""
    await revoke_token("not.a.jwt")
    await revoke_token("")
    await revoke_token(None)


@pytest.mark.asyncio
async def test_revoke_does_not_invalidate_other_tokens():
    """Each user can have multiple sessions (different browsers); only
    the specific token being logged out should be invalidated."""
    from fastapi import HTTPException, status
    t1 = create_access_token({"sub": "alice"})
    t2 = create_access_token({"sub": "alice"})
    await revoke_token(t1)

    exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="x")
    # t1 revoked
    with pytest.raises(HTTPException):
        await verify_token(t1, exc)
    # t2 still valid
    data = await verify_token(t2, exc)
    assert data.username == "alice"
