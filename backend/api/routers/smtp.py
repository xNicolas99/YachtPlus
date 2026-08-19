from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import smtplib
import logging
from email.mime.text import MIMEText
import asyncio
from api.utils.auth import get_db
from api.db.models.settings import SMTPSettings
from api.auth.jwt import get_auth_wrapper
from api.auth.auth import auth_check, require_superuser
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter()

class SMTPSettingsSchema(BaseModel):
    server: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    sender_email: EmailStr
    use_tls: bool = True

class TestEmailSchema(BaseModel):
    recipient: EmailStr


def _send_test_email_sync(settings, recipient: str) -> None:
    """Synchronous SMTP send, run in a thread so it never blocks the loop."""
    msg = MIMEText("This is a test email from YachtPlus.")
    msg['Subject'] = 'YachtPlus Test Email'
    msg['From'] = settings.sender_email
    msg['To'] = recipient

    try:
        if settings.use_tls:
            server = smtplib.SMTP(settings.server, settings.port)
            server.starttls()
        else:
            server = smtplib.SMTP(settings.server, settings.port)

        if settings.username and settings.password:
            server.login(settings.username, settings.password)

        server.sendmail(settings.sender_email, recipient, msg.as_string())
        server.quit()
    except Exception:
        logger.exception("SMTP test failed for recipient %s", recipient)
        raise HTTPException(
            status_code=500,
            detail="SMTP test failed. Check server logs for details.",
        )


@router.get("/", response_model=SMTPSettingsSchema)
async def get_smtp_settings(db: AsyncSession = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    await auth_check(Authorize)
    result = await db.execute(select(SMTPSettings).limit(1))
    settings = result.scalars().first()
    if not settings:
        # Return default or empty
        return SMTPSettingsSchema(server="", port=587, sender_email="admin@example.com")
    return settings

@router.post("/", response_model=SMTPSettingsSchema)
async def update_smtp_settings(settings: SMTPSettingsSchema, db: AsyncSession = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    # SMTP server credentials are instance-global config. A non-admin who
    # could overwrite them could redirect alert mail to a domain they
    # control (credential phish / silent alerting downgrade) — superuser
    # only.
    await require_superuser(Authorize, db)
    result = await db.execute(select(SMTPSettings).limit(1))
    db_settings = result.scalars().first()
    if not db_settings:
        db_settings = SMTPSettings(**settings.dict())
        db.add(db_settings)
    else:
        for key, value in settings.dict().items():
            setattr(db_settings, key, value)
    await db.commit()
    await db.refresh(db_settings)
    return db_settings

@router.post("/test")
async def send_test_email(email_data: TestEmailSchema, db: AsyncSession = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    # Without a superuser gate this route is an authenticated open relay:
    # any user can fire mail through the configured SMTP server to any
    # arbitrary recipient, which is both a spam vector and a way to burn
    # the configured mail server's reputation.
    await require_superuser(Authorize, db)
    result = await db.execute(select(SMTPSettings).limit(1))
    settings = result.scalars().first()
    if not settings:
        raise HTTPException(status_code=400, detail="SMTP settings not configured")

    # SMTP is blocking network I/O — run it in a thread so the event loop stays free.
    await asyncio.to_thread(_send_test_email_sync, settings, email_data.recipient)
    return {"message": "Test email sent successfully"}
