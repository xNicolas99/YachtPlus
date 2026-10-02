"""Consume a valid TOTP time step atomically across workers."""
import asyncio
import time
import pyotp
from sqlalchemy import update, or_
from api.db.models.users import User
from api.utils.crypto import decrypt

async def consume_totp(db, user, code):
    secret = await asyncio.to_thread(decrypt, user.otp_secret)
    totp = pyotp.TOTP(secret)
    now = time.time()
    if not isinstance(code, str):
        return False
    current = int(now // totp.interval)
    # Preserve RFC 6238 clock tolerance while consuming the actual matched
    # counter, so a code cannot be replayed in an adjacent time window.
    step = next((counter for counter in (current, current - 1, current + 1)
                 if counter >= 0 and totp.verify(code, for_time=counter * totp.interval)), None)
    if step is None:
        return False
    result = await db.execute(update(User).where(
        User.id == user.id, User.otp_secret == user.otp_secret,
        or_(User.otp_last_step.is_(None), User.otp_last_step < step),
    ).values(otp_last_step=step))
    if result.rowcount != 1:
        return False
    await db.commit()
    return True
