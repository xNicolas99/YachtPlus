from sqlalchemy.orm import Session
from api.db.models.audit import AuditLog
import logging

logger = logging.getLogger(__name__)

def log_activity(db: Session, user: str, action: str, resource: str = None, details: str = None):
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
        db.commit()
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")
        db.rollback()
