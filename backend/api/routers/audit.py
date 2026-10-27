import csv
import io
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from api.utils.auth import get_db
from api.db.models.audit import AuditLog
from api.auth.jwt import get_auth_wrapper
from api.auth.auth import require_superuser
from pydantic import BaseModel, ConfigDict

router = APIRouter()

class AuditLogOut(BaseModel):
    id: int
    timestamp: datetime
    user: str
    action: str
    resource: Optional[str] = None
    details: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AuditPage(BaseModel):
    items: List[AuditLogOut]
    total: int
    limit: int
    offset: int


def _conditions(user=None, action=None, resource=None, since=None, until=None):
    conditions = []
    for value, column in ((user, AuditLog.user), (action, AuditLog.action)):
        if value:
            if len(value) > 264:
                raise HTTPException(422, "Audit filter is too long")
            conditions.append(column == value)
    if resource:
        if len(resource) > 255:
            raise HTTPException(422, "Resource filter is too long")
        conditions.append(AuditLog.resource.contains(resource, autoescape=True))
    since = since.replace(tzinfo=timezone.utc) if since and since.tzinfo is None else since
    until = until.replace(tzinfo=timezone.utc) if until and until.tzinfo is None else until
    since = since.astimezone(timezone.utc) if since else None
    until = until.astimezone(timezone.utc) if until else None
    if since and until and since > until:
        raise HTTPException(422, "Start time must precede end time")
    if since:
        conditions.append(AuditLog.timestamp >= since)
    if until:
        conditions.append(AuditLog.timestamp <= until)
    return conditions


async def _page(db, *, limit, offset, conditions):
    if not 1 <= limit <= 200 or not 0 <= offset <= 1_000_000:
        raise HTTPException(422, "Invalid audit pagination")
    total = (await db.execute(select(func.count()).select_from(AuditLog).where(*conditions))).scalar_one()
    result = await db.execute(
        select(AuditLog).where(*conditions)
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(limit).offset(offset)
    )
    return {"items": result.scalars().all(), "total": total, "limit": limit, "offset": offset}


@router.get("/entries", response_model=AuditPage)
async def get_audit_entries(
    limit: int = 50, offset: int = 0,
    user: Optional[str] = None, action: Optional[str] = None, resource: Optional[str] = None,
    since: Optional[datetime] = None, until: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db), Authorize=Depends(get_auth_wrapper),
):
    await require_superuser(Authorize, db)
    return await _page(db, limit=limit, offset=offset,
                       conditions=_conditions(user, action, resource, since, until))


def _csv_value(value):
    text = "" if value is None else str(value)
    # Quoting alone does not stop spreadsheet formula execution.
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r")) else text


@router.get("/export")
async def export_audit_entries(
    user: Optional[str] = None, action: Optional[str] = None, resource: Optional[str] = None,
    since: Optional[datetime] = None, until: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db), Authorize=Depends(get_auth_wrapper),
):
    await require_superuser(Authorize, db)
    conditions = _conditions(user, action, resource, since, until)
    total = (await db.execute(select(func.count()).select_from(AuditLog).where(*conditions))).scalar_one()
    rows = (await db.execute(select(AuditLog).where(*conditions)
                            .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(5000))).scalars().all()
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Timestamp (UTC)", "User", "Action", "Resource", "Details"])
    for row in rows:
        timestamp = row.timestamp
        if timestamp and timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        timestamp = timestamp.astimezone(timezone.utc).isoformat() if timestamp else ""
        writer.writerow([_csv_value(value) for value in (timestamp, row.user, row.action, row.resource, row.details)])
    return Response(
        output.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="yachtplus-audit.csv"',
                 "X-Total-Count": str(total), "X-Export-Limit": "5000", "Cache-Control": "no-store"},
    )

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
