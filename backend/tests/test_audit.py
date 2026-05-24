import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi import HTTPException
from api.db.database import Base
from api.db.models.audit import AuditLog
from api.db.models.users import User
from api.routers.audit import get_audit_logs, get_db

engine = create_engine('sqlite:///:memory:')
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

class MockAuthValid:
    def __init__(self, username="admin"):
        self.username = username
    def jwt_required(self, allow_setup_pending=False):
        return True
    def get_jwt_subject(self, allow_setup_pending=False):
        return self.username

class MockAuthInvalid:
    def jwt_required(self, allow_setup_pending=False):
        raise HTTPException(status_code=401, detail="Unauthorized")

@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    # /audit/ is superuser-gated now; seed the admin user that MockAuthValid
    # resolves to so require_superuser passes.
    db.add(User(username="admin", hashed_password="pw", is_superuser=True))
    db.commit()
    yield db
    db.close()

def test_get_db():
    """Test the get_db dependency yields a session and then closes it."""
    db_gen = get_db()
    db_session = next(db_gen)
    assert isinstance(db_session, Session)

    # Fast forward the generator to hit the finally block and close the session
    with pytest.raises(StopIteration):
        next(db_gen)

def test_get_audit_logs(db):
    """Test retrieving audit logs returns them in descending timestamp order."""
    now = datetime.now(timezone.utc)
    log1 = AuditLog(user="admin", action="login", resource="auth", details="Successful login", timestamp=now - timedelta(seconds=10))
    log2 = AuditLog(user="admin", action="create_container", resource="test-container", details="Container created", timestamp=now)
    db.add_all([log1, log2])
    db.commit()

    auth = MockAuthValid("admin")
    logs = get_audit_logs(limit=10, db=db, Authorize=auth)

    assert len(logs) == 2
    # Ensure descending order
    assert logs[0].action == "create_container"
    assert logs[1].action == "login"

def test_get_audit_logs_limit(db):
    """Test that the limit parameter correctly restricts the number of returned logs."""
    now = datetime.now(timezone.utc)
    logs_to_add = []
    for i in range(15):
        log = AuditLog(user="admin", action=f"action_{i}", resource="test-container", details=f"Details {i}", timestamp=now + timedelta(seconds=i))
        logs_to_add.append(log)
    db.add_all(logs_to_add)
    db.commit()

    auth = MockAuthValid("admin")
    logs = get_audit_logs(limit=5, db=db, Authorize=auth)

    assert len(logs) == 5
    # Since logs are created with increasing timestamps, action_14 is the latest
    assert logs[0].action == "action_14"
    assert logs[4].action == "action_10"

def test_get_audit_logs_unauthorized(db):
    """Test that retrieving audit logs without valid authentication raises a 401 Unauthorized."""
    auth = MockAuthInvalid()
    with pytest.raises(HTTPException) as excinfo:
        get_audit_logs(limit=10, db=db, Authorize=auth)
    assert excinfo.value.status_code == 401

def test_get_audit_logs_empty(db):
    """Test retrieving audit logs when none exist."""
    auth = MockAuthValid("admin")
    logs = get_audit_logs(limit=10, db=db, Authorize=auth)
    assert len(logs) == 0
