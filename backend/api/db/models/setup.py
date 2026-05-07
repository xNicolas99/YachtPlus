from sqlalchemy import Boolean, Column, Integer, DateTime
from sqlalchemy.sql import func
from api.db.database import Base

class SetupStatus(Base):
    __tablename__ = "setup_status"

    id = Column(Integer, primary_key=True, index=True)
    is_complete = Column(Boolean, default=False)
    is_bypassed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
