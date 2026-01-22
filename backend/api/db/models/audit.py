from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from api.db.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user = Column(String, index=True)
    action = Column(String, index=True)
    resource = Column(String, nullable=True) # ID or name of the resource (e.g. container name)
    details = Column(Text, nullable=True)
