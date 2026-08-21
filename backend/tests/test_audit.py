import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException
from api.db.database import Base
from api.db.models.audit import AuditLog
from api.db.models.users import User
from api.routers.audit import get_audit_logs

engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

class MockAuthValid:
    def __init__(self, username="admin"):
        self.username = username
    async def jwt_required(self, allow_setup_pending=False):
        return True
    async def get_jwt_subject(self, allow_setup_pending=False):
        return self.username

class MockAuthInvalid:
    async def jwt_required(self, allow_setup_pending=False):
        raise HTTPException(status_code=401, detail="Unauthorized")

@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        # /audit/ is superuser-gated now; seed the admin user that MockAuthValid
        # resolves to so require_superuser passes.
        db.add(User(username="admin", hashed_password="pw", is_superuser=True))
        await db.commit()
        yield db

@pytest.mark.asyncio
async def test_get_audit_logs(db):
    """Test retrieving audit logs returns them in descending timestamp order."""
    now = datetime.now(timezone.utc)
    log1 = AuditLog(user="admin", action="login", resource="auth", details="Successful login", timestamp=now - timedelta(seconds=10))
    log2 = AuditLog(user="admin", action="create_container", resource="test-container", details="Container created", timestamp=now)
    db.add_all([log1, log2])
    await db.commit()

    auth = MockAuthValid("admin")
    logs = await get_audit_logs(limit=10, db=db, Authorize=auth)

    assert len(logs) == 2
    # Ensure descending order
    assert logs[0].action == "create_container"
    assert logs[1].action == "login"

@pytest.mark.asyncio
async def test_get_audit_logs_limit(db):
    """Test that the limit parameter correctly restricts the number of returned logs."""
    now = datetime.now(timezone.utc)
    logs_to_add = []
    for i in range(15):
        log = AuditLog(user="admin", action=f"action_{i}", resource="test-container", details=f"Details {i}", timestamp=now + timedelta(seconds=i))
        logs_to_add.append(log)
    db.add_all(logs_to_add)
    await db.commit()

    auth = MockAuthValid("admin")
    logs = await get_audit_logs(limit=5, db=db, Authorize=auth)

    assert len(logs) == 5
    # Since logs are created with increasing timestamps, action_14 is the latest
    assert logs[0].action == "action_14"
    assert logs[4].action == "action_10"

@pytest.mark.asyncio
async def test_get_audit_logs_unauthorized(db):
    """Test that retrieving audit logs without valid authentication raises a 401 Unauthorized."""
    auth = MockAuthInvalid()
    with pytest.raises(HTTPException) as excinfo:
        await get_audit_logs(limit=10, db=db, Authorize=auth)
    assert excinfo.value.status_code == 401

@pytest.mark.asyncio
async def test_get_audit_logs_empty(db):
    """Test retrieving audit logs when none exist."""
    auth = MockAuthValid("admin")
    logs = await get_audit_logs(limit=10, db=db, Authorize=auth)
    assert len(logs) == 0
