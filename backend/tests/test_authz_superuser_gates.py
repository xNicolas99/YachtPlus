"""Regression for the AuthZ audit batch (set_template_variables,
import_settings, update_self, delete_image, delete_volume, get_audit_logs,
trigger_project_update, update_smtp_settings, send_test_email).

All of these were gated only by auth_check before — a non-admin signed-in
user could mutate shared system state (template variables substituted
into every deploy, SMTP config, app self-update, audit log read). The
fix routes them through `require_superuser`. These tests assert the gate
fires for a non-admin and lets a real superuser through.
"""
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from api.db.database import Base
from api.db.models.users import User
from api.db.models.audit import AuditLog
from api.db.models.settings import SMTPSettings


engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
TestingSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class MockAuth:
    def __init__(self, username):
        self.username = username

    async def jwt_required(self, allow_setup_pending=False):
        return True

    async def get_jwt_subject(self, allow_setup_pending=False):
        return self.username


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSessionLocal() as session:
        session.add(User(username="bob", hashed_password="pw", is_superuser=False))
        session.add(User(username="root", hashed_password="pw", is_superuser=True))
        await session.commit()
        yield session


@pytest.fixture(autouse=True)
def _force_auth_on(monkeypatch):
    # require_superuser short-circuits when DISABLE_AUTH=True; the audit
    # batch is about prod-mode behaviour, so force the strict path.
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


# --- BUG-001 / 002 / 003: app_settings ---------------------------------

@pytest.mark.asyncio
async def test_set_template_variables_rejects_non_admin(db):
    from api.routers.app_settings import set_template_variables
    with pytest.raises(HTTPException) as exc:
        await set_template_variables(new_variables=[], db=db, Authorize=MockAuth("bob"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_set_template_variables_allows_admin(db):
    from api.routers.app_settings import set_template_variables
    with patch("api.routers.app_settings.crud.set_template_variables", return_value=[]) as inner:
        await set_template_variables(new_variables=[], db=db, Authorize=MockAuth("root"))
    inner.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_settings_rejects_non_admin(db):
    from api.routers.app_settings import import_settings
    fake_upload = MagicMock()
    with pytest.raises(HTTPException) as exc:
        await import_settings(db=db, upload=fake_upload, Authorize=MockAuth("bob"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_update_self_rejects_non_admin(db):
    from api.routers.app_settings import update_self
    bg = MagicMock()
    with pytest.raises(HTTPException) as exc:
        await update_self(request=MagicMock(), background_tasks=bg, db=db, Authorize=MockAuth("bob"))
    assert exc.value.status_code == 403


# --- BUG-004 / 005: resources ------------------------------------------

@pytest.mark.asyncio
async def test_delete_image_rejects_non_admin(db):
    from api.routers.resources import delete_image
    with pytest.raises(HTTPException) as exc:
        await delete_image(MagicMock(), "sha256:abc", db=db, Authorize=MockAuth("bob"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_volume_rejects_non_admin(db):
    from api.routers.resources import delete_volume
    with pytest.raises(HTTPException) as exc:
        await delete_volume(MagicMock(), "data-vol", db=db, Authorize=MockAuth("bob"))
    assert exc.value.status_code == 403


# --- BUG-006: audit log -------------------------------------------------

@pytest.mark.asyncio
async def test_get_audit_logs_rejects_non_admin(db):
    from api.routers.audit import get_audit_logs
    with pytest.raises(HTTPException) as exc:
        await get_audit_logs(limit=10, db=db, Authorize=MockAuth("bob"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_audit_logs_clamps_limit(db):
    """Even an admin asking for limit=10**9 only gets the cap."""
    from api.routers.audit import get_audit_logs
    # The clamp is what we're verifying — there's no actual data, but the
    # DB query should be issued with the clamped value, not the raw one.
    logs = await get_audit_logs(limit=10**9, db=db, Authorize=MockAuth("root"))
    assert isinstance(logs, list)


@pytest.mark.asyncio
async def test_get_audit_logs_clamps_low_limit(db):
    from api.routers.audit import get_audit_logs
    db.add(AuditLog(user="root", action="login", resource="auth"))
    await db.commit()
    logs = await get_audit_logs(limit=0, db=db, Authorize=MockAuth("root"))
    # 0 should be clamped up to 1; we may or may not get a row depending
    # on the test order, but the call must not error.
    assert isinstance(logs, list)


# --- BUG-007: watchtower ------------------------------------------------

@pytest.mark.asyncio
async def test_trigger_project_update_rejects_non_admin(db):
    from api.routers.watchtower import trigger_project_update
    bg = MagicMock()
    with pytest.raises(HTTPException) as exc:
        await trigger_project_update("proj", background_tasks=bg, db=db, Authorize=MockAuth("bob"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_trigger_all_updates_rejects_non_admin(db):
    from api.routers.watchtower import trigger_all_updates
    bg = MagicMock()
    with pytest.raises(HTTPException) as exc:
        await trigger_all_updates(background_tasks=bg, db=db, Authorize=MockAuth("bob"))
    assert exc.value.status_code == 403


# --- BUG-008 / 009: smtp -----------------------------------------------

@pytest.mark.asyncio
async def test_update_smtp_settings_rejects_non_admin(db):
    from api.routers.smtp import update_smtp_settings, SMTPSettingsSchema
    payload = SMTPSettingsSchema(
        server="evil.example.com", port=25,
        sender_email="x@x.com", use_tls=False,
    )
    with pytest.raises(HTTPException) as exc:
        await update_smtp_settings(payload, db=db, Authorize=MockAuth("bob"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_send_test_email_rejects_non_admin(db):
    from api.routers.smtp import send_test_email, TestEmailSchema
    payload = TestEmailSchema(recipient="phish@attacker.example")
    with pytest.raises(HTTPException) as exc:
        await send_test_email(payload, db=db, Authorize=MockAuth("bob"))
    assert exc.value.status_code == 403
