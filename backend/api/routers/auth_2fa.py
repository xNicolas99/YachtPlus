from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import asyncio
from api.utils.auth import get_db
from api.db.models.users import User
from api.auth.jwt import get_auth_wrapper
from api.auth.auth import auth_check, auth_check_setup_pending
from api.utils.crypto import encrypt, decrypt
from api.db.crud.users import verify_password
import pyotp
import qrcode
import io
import base64

router = APIRouter()


def _generate_qr_code_sync(provisioning_uri: str) -> str:
    """Synchronous QR code generation (CPU-bound). Runs in a thread."""
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()


@router.get("/generate")
async def generate_2fa_get(
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    """GET version of generate_2fa for consistency with frontend request"""
    return await generate_2fa_logic(db, Authorize)


@router.post("/generate")
async def generate_2fa(
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    return await generate_2fa_logic(db, Authorize)


async def generate_2fa_logic(db: AsyncSession, Authorize: get_auth_wrapper):
    await auth_check_setup_pending(Authorize, db)
    username = await Authorize.get_jwt_subject(allow_setup_pending=True)
    result = await db.execute(select(User).filter(User.username == username))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate secret
    secret = pyotp.random_base32()
    # Encrypt before storing
    user.otp_secret = encrypt(secret)
    await db.commit()

    # Generate QR Code
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=user.username, issuer_name="YachtPlus"
    )

    # QR generation is CPU-bound; run it in a thread so we don't block the loop.
    img_str = await asyncio.to_thread(_generate_qr_code_sync, provisioning_uri)

    # Return raw secret to user for manual entry if needed (stored encrypted)
    return {
        "secret": secret,
        "qr_code": f"data:image/png;base64,{img_str}",
        "provisioning_uri": provisioning_uri
    }


class TwoFactorRequest(BaseModel):
    secret: Optional[str] = None
    code: str


@router.post("/enable")
async def enable_2fa(
    payload: TwoFactorRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    # Support both {code: "123456"} and {secret: "...", code: "123456"}
    # The frontend is sending {secret, code}.
    # However, we store the secret in DB encrypted already in generate step.
    # We should trust DB secret over frontend secret for security.

    await auth_check_setup_pending(Authorize, db)
    username = await Authorize.get_jwt_subject(allow_setup_pending=True)
    result = await db.execute(select(User).filter(User.username == username))
    user = result.scalars().first()

    if not user or not user.otp_secret:
        raise HTTPException(status_code=400, detail="2FA setup not initiated")

    try:
        # Decrypt secret from DB (Ground Truth)
        secret = decrypt(user.otp_secret)

        # Verify code
        totp = pyotp.TOTP(secret)
        if totp.verify(payload.code):
            user.is_2fa_enabled = True
            await db.commit()
            return {"message": "2FA enabled successfully"}
        else:
            raise HTTPException(status_code=400, detail="Invalid code")
    except Exception as e:
        print(f"2FA Enable Error: {e}")
        raise HTTPException(
            status_code=400, detail="Invalid token or secret error"
        )


class Disable2FARequest(BaseModel):
    # Password reconfirmation is required to disable 2FA. Without it, a
    # hijacked session (XSS, stolen cookie, leaked API key) could drop
    # the user's second factor and downgrade them to single-factor auth
    # without ever needing the password — defeating the point of 2FA.
    password: str
    code: Optional[str] = None


@router.post("/disable")
async def disable_2fa(
    payload: Disable2FARequest = Body(...),
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    username = await Authorize.get_jwt_subject()
    result = await db.execute(select(User).filter(User.username == username))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not await verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Password incorrect")

    # If 2FA is currently enabled we additionally require a fresh TOTP
    # code so the disable path can't be completed purely from the session
    # cookie + a leaked/old password. The code check is skipped if 2FA
    # was never enabled (idempotent disable).
    if user.is_2fa_enabled:
        if not payload.code:
            raise HTTPException(status_code=400, detail="2FA code required")
        try:
            secret = decrypt(user.otp_secret)
            totp = pyotp.TOTP(secret)
            if not totp.verify(payload.code):
                raise HTTPException(status_code=400, detail="Invalid 2FA code")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid 2FA code")

    user.is_2fa_enabled = False
    user.otp_secret = None
    await db.commit()
    return {"message": "2FA disabled successfully"}
