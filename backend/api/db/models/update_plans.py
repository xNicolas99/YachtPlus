"""Explicit administrator-approved maintenance windows for Compose projects."""

from datetime import datetime, timezone
import secrets

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String

from api.db.database import Base


class UpdatePlan(Base):
    __tablename__ = "update_plan"

    project_name = Column(String(128), primary_key=True)
    enabled = Column(Boolean, nullable=False, default=False)
    excluded = Column(Boolean, nullable=False, default=False)
    weekdays = Column(JSON, nullable=False, default=lambda: list(range(7)))
    window_start_hour = Column(Integer, nullable=False, default=0)
    window_end_hour = Column(Integer, nullable=False, default=24)
    cadence_days = Column(Integer, nullable=False, default=1)
    owner_id = Column(Integer, nullable=True)
    owner_username = Column(String(264), nullable=True)
    owner_auth_version = Column(String(64), nullable=True)
    revision = Column(String(32), nullable=False, default=lambda: secrets.token_hex(16))
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))
    last_run = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(String(16), nullable=False, default="never")
    last_error = Column(String(255), nullable=True)
    last_operation_id = Column(String(36), nullable=True)
