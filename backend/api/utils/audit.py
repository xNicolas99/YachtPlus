from sqlalchemy.ext.asyncio import AsyncSession
from api.db.models.audit import AuditLog
import logging

logger = logging.getLogger(__name__)


async def log_activity(db: AsyncSession, user: str, action: str, resource: str = None, details: str = None):
    """
    Logs a critical activity to the database.
    """
    try:
        audit = AuditLog(
            user=user,
            action=action,
            resource=resource,
            details=details
        )
        db.add(audit)
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")
        await db.rollback()
