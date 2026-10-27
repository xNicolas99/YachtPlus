"""Volume archive metadata and opt-in daily backup policies."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String

from api.db.database import Base


class VolumeBackup(Base):
    __tablename__ = "volume_backups"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    volume = Column(String(255), nullable=False, index=True)
    created_by = Column(String(264), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    status = Column(String(20), nullable=False, default="queued")
    size_bytes = Column(BigInteger, nullable=True)
    sha256 = Column(String(64), nullable=True)
    error = Column(String(200), nullable=True)
    operation_id = Column(String(36), nullable=True)


class BackupSchedule(Base):
    __tablename__ = "backup_schedules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    volume = Column(String(255), nullable=False, unique=True)
    enabled = Column(Boolean, nullable=False, default=False)
    hour_utc = Column(Integer, nullable=False, default=2)
    minute_utc = Column(Integer, nullable=False, default=0)
    retain_count = Column(Integer, nullable=False, default=7)
    confirm_live = Column(Boolean, nullable=False, default=False)
    created_by = Column(String(264), nullable=False)
    created_by_id = Column(Integer, nullable=False)
    created_by_version = Column(String(64), nullable=False)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(String(200), nullable=True)
