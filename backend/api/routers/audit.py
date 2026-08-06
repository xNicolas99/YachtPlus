from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from api.utils.auth import get_db
from api.db.models.audit import AuditLog
from api.auth.jwt import get_auth_wrapper
from api.auth.auth import auth_check, require_superuser
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class AuditLogOut(BaseModel):
    id: int
    timestamp: datetime
    user: str
    action: str
    resource: Optional[str] = None
    details: Optional[str] = None

    class Config:
        from_attributes = True

@router.get("/", response_model=List[AuditLogOut])
async def get_audit_logs(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    """
    Fetch the latest audit logs.
    """
    # Audit log leaks who did what to which container plus admin usernames;
    # gate behind superuser so a low-privileged operator can't enumerate
    # admin activity or use the log as a reconnaissance channel.
    await require_superuser(Authorize, db)
    # Clamp limit so a hostile caller can't request the whole table.
    if limit < 1:
        limit = 1
    if limit > 1000:
        limit = 1000
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    )
    logs = result.scalars().all()
    return logs
