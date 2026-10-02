"""Registration must not reassign an unfinished setup account."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request, Response
from httpx import ASGITransport, AsyncClient
import pyotp
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.db.database import Base
from api.db.models.users import User
from api.db.models.setup import SetupRegistrationClaim
from api.db.schemas.users import UserCreate
from api.routers.setup.setup import register_first_user
from api.db.crud.users import get_user_by_name
from api.main import app, _setup_status_cache
from api.utils.auth import get_db


@pytest.mark.asyncio
async def test_registration_resume_requires_original_password_and_single_account(db):
    request = Request({"type": "http", "method": "POST", "path": "/api/setup/register", "headers": []})
    auth = MagicMock()

    with patch("api.routers.setup.setup.is_setup_completed_async", return_value=False):
        created = await register_first_user(
            request, Response(), UserCreate(username="admin", password="original"), db, auth
        )
        assert created["username"] == "admin"

        result = await db.execute(select(User))
        original = result.scalar_one()
        original_hash = original.hashed_password

        with pytest.raises(HTTPException) as wrong_password:
            await register_first_user(
                request, Response(), UserCreate(username="admin", password="attacker"), db, auth
            )
        assert wrong_password.value.status_code == 401

        with pytest.raises(HTTPException) as second_account:
            await register_first_user(
                request, Response(), UserCreate(username="attacker", password="attacker"), db, auth
            )
        assert second_account.value.status_code == 403

        resumed = await register_first_user(
            request, Response(), UserCreate(username="admin", password="original"), db, auth
        )
        assert resumed["username"] == "admin"

    await db.refresh(original)
    assert original.hashed_password == original_hash
    assert original.is_superuser is True
    assert original.is_active is False
    assert (await db.execute(select(func.count()).select_from(User))).scalar_one() == 1
    assert auth.set_access_cookies.call_count == 2


@pytest.mark.asyncio
async def test_parallel_first_registration_creates_exactly_one_admin(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'parallel.db').as_posix()}")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    ready = asyncio.Event()
    arrivals = 0

    async def synchronized_lookup(db, username):
        nonlocal arrivals
        found = await get_user_by_name(db, username)
        arrivals += 1
        if arrivals == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), timeout=10)
        return found

    async def attempt(username):
        async with sessions() as db:
            request = Request({"type": "http", "method": "POST", "path": "/api/setup/register", "headers": []})
            return await register_first_user(
                request, Response(), UserCreate(username=username, password="password"), db, MagicMock()
            )

    try:
        with patch("api.routers.setup.setup.is_setup_completed_async", return_value=False), \
             patch("api.routers.setup.setup.get_user_by_name", new=synchronized_lookup):
            outcomes = await asyncio.gather(attempt("admin_a"), attempt("admin_b"), return_exceptions=True)

        successes = [outcome for outcome in outcomes if isinstance(outcome, dict)]
        refusals = [outcome for outcome in outcomes if isinstance(outcome, HTTPException)]
        assert len(successes) == 1, outcomes
        assert len(refusals) == 1, outcomes
        assert refusals[0].status_code == 409

        async with sessions() as db:
            assert (await db.execute(select(func.count()).select_from(User))).scalar_one() == 1
            assert (await db.execute(select(func.count()).select_from(SetupRegistrationClaim))).scalar_one() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_complete_first_run_via_api(db, tmp_path, monkeypatch):
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def auth_db():
        yield db
    monkeypatch.setattr("api.db.database.SessionLocal", auth_db)
    async def test_db():
        yield db

    app.dependency_overrides[get_db] = test_db
    _setup_status_cache.clear()
    try:
        with patch("api.routers.setup.setup.SETUP_FLAG_FILE", str(tmp_path / "setup-complete")), \
             patch("api.db.crud.templates.init_templates_async", new=AsyncMock()):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
                registered = await client.post(
                    "/api/setup/register", json={"username": "admin", "password": "original"}
                )
                assert registered.status_code == 200, registered.text
                assert "access_token_cookie" in client.cookies

                client.headers["X-CSRF-TOKEN"] = client.cookies["csrf_access_token"]
                generated = await client.post("/api/auth/2fa/generate")
                assert generated.status_code == 200, generated.text
                code = pyotp.TOTP(generated.json()["secret"]).now()

                enabled = await client.post("/api/auth/2fa/enable", json={"code": code})
                assert enabled.status_code == 200, enabled.text

                finalized = await client.post("/api/setup/finalize")
                assert finalized.status_code == 200, finalized.text
                assert finalized.json() == {"message": "Setup finalized"}

                status = await client.get("/api/setup/status")
                assert status.json() == {"is_setup": True}

                _setup_status_cache.clear()
                me = await client.get("/api/auth/me")
                assert me.status_code == 200, me.text
                assert me.json()["is_active"] is True
    finally:
        app.dependency_overrides.clear()
        _setup_status_cache.clear()
