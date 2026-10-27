"""Durable, credential-free status records for operator initiated work."""

from datetime import datetime, timezone
import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from api.db.database import Base


class Operation(Base):
    __tablename__ = "operation"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    kind = Column(String(64), nullable=False, index=True)
    resource = Column(String(512), nullable=False)
    action = Column(String(32), nullable=True)
    actor = Column(String(264), nullable=False, index=True)
    actor_id = Column(Integer, nullable=False)
    actor_instance = Column(String(36), nullable=False)
    auth_version = Column(String(64), nullable=True)
    retry_supported = Column(Boolean, nullable=False, default=False)
    worker_id = Column(String(36), nullable=False, index=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(16), nullable=False, default="queued", index=True)
    phase = Column(String(120), nullable=False, default="Waiting for a worker")
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
