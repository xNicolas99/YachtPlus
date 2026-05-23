"""Regression for BUG-005: distributed brute-force across IPs against the
same username was undetected. The per-username failed-attempt counter now
locks the account temporarily.
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.database import Base
from api.db.models.users import LoginAttempt
from api.utils.security import (
    check_ip_restriction,
    _count_recent_failed_attempts_for_username,
    _USERNAME_LOCKOUT_THRESHOLD,
)


engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    yield s
    s.close()


def _seed_failed_attempts(db, *, username, count, base_ip="10.0.0.{}"):
    """Spread failed attempts across many IPs so the per-IP gate doesn't
    fire — exactly the distributed-brute-force scenario."""
    for i in range(count):
        db.add(LoginAttempt(
            ip_address=base_ip.format(i % 250),
            username=username,
            success=False,
            timestamp=datetime.utcnow(),
        ))
    db.commit()


def _make_request(host="10.0.0.1"):
    req = MagicMock()
    req.client.host = host
    req.headers = {}
    return req


def test_per_username_count_helper(db):
    _seed_failed_attempts(db, username="alice", count=7)
    # Noise: another user shouldn't affect alice's count.
    _seed_failed_attempts(db, username="bob", count=50)
    assert _count_recent_failed_attempts_for_username(db, "alice") == 7


def test_old_attempts_dont_count(db):
    old = datetime.utcnow() - timedelta(hours=2)
    for _ in range(_USERNAME_LOCKOUT_THRESHOLD + 5):
        db.add(LoginAttempt(
            ip_address="10.0.0.5", username="alice", success=False, timestamp=old,
        ))
    db.commit()
    assert _count_recent_failed_attempts_for_username(db, "alice", minutes=30) == 0


def test_distributed_brute_force_triggers_lockout(db):
    # Each IP only has a single failure (well below the per-IP fail2ban
    # threshold of 5), but the username has many across the botnet.
    _seed_failed_attempts(db, username="alice", count=_USERNAME_LOCKOUT_THRESHOLD)

    # A *new* IP that has never failed before now tries to log in as alice.
    request = _make_request(host="10.0.99.99")

    with patch("api.utils.security.send_security_alert") as alert:
        with pytest.raises(HTTPException) as exc:
            check_ip_restriction(request, db, username="alice")

    assert exc.value.status_code == 403
    assert "locked" in exc.value.detail.lower()
    alert.assert_called_once()


def test_below_threshold_is_allowed(db):
    _seed_failed_attempts(db, username="alice", count=_USERNAME_LOCKOUT_THRESHOLD - 1)
    request = _make_request(host="10.0.99.99")
    # Should not raise: per-IP count is 0 and per-username count is below threshold.
    assert check_ip_restriction(request, db, username="alice") == "10.0.99.99"


def test_other_users_not_affected_when_one_user_locked(db):
    _seed_failed_attempts(db, username="alice", count=_USERNAME_LOCKOUT_THRESHOLD + 5)
    request = _make_request(host="10.0.99.99")
    # bob has no failed attempts -> login attempt should pass.
    assert check_ip_restriction(request, db, username="bob") == "10.0.99.99"


def test_lockout_skipped_when_username_not_supplied(db):
    """Username-less callers (introspection / system probes) should not be
    blocked by a totally unrelated user's lockout."""
    _seed_failed_attempts(db, username="alice", count=_USERNAME_LOCKOUT_THRESHOLD + 5)
    request = _make_request(host="10.0.99.99")
    # No username -> per-username check is skipped.
    assert check_ip_restriction(request, db, username=None) == "10.0.99.99"
