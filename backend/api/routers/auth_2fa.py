from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from api.db.database import SessionLocal
from api.db.models.users import User
from api.auth.jwt import get_auth_wrapper
from api.auth.auth import auth_check, auth_check_setup_pending
from api.utils.crypto import encrypt, decrypt
import pyotp
import qrcode
import io
import base64

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/generate")
def generate_2fa_get(db: Session = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    """GET version of generate_2fa for consistency with frontend request"""
    return generate_2fa_logic(db, Authorize)

@router.post("/generate")
def generate_2fa(db: Session = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    return generate_2fa_logic(db, Authorize)

def generate_2fa_logic(db: Session, Authorize: get_auth_wrapper):
    auth_check_setup_pending(Authorize)
    username = Authorize.get_jwt_subject(allow_setup_pending=True)
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate secret
    secret = pyotp.random_base32()
    # Encrypt before storing
    user.otp_secret = encrypt(secret)
    db.commit()

    # Generate QR Code
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=user.username, issuer_name="YachtPlus")

    # Use more standard QR generation with better styling options if needed, but basic is fine
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()

    # Return the raw secret to the user for manual entry if needed, but it's stored encrypted
    return {
        "secret": secret,
        "qr_code": f"data:image/png;base64,{img_str}",
        "provisioning_uri": provisioning_uri
    }

class TwoFactorRequest(BaseModel):
    secret: Optional[str] = None
    code: str

@router.post("/enable")
def enable_2fa(
    payload: TwoFactorRequest = Body(...),
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    # Support both {code: "123456"} and {secret: "...", code: "123456"}
    # The frontend is sending {secret, code}.
    # However, we store the secret in DB encrypted already in generate step.
    # We should trust DB secret over frontend secret for security, but we can verify.

    auth_check_setup_pending(Authorize)
    username = Authorize.get_jwt_subject(allow_setup_pending=True)
    user = db.query(User).filter(User.username == username).first()

    if not user or not user.otp_secret:
        raise HTTPException(status_code=400, detail="2FA setup not initiated")

    try:
        # Decrypt secret from DB (Ground Truth)
        secret = decrypt(user.otp_secret)

        # Verify code
        totp = pyotp.TOTP(secret)
        if totp.verify(payload.code):
            user.is_2fa_enabled = True
            db.commit()
            return {"message": "2FA enabled successfully"}
        else:
            raise HTTPException(status_code=400, detail="Invalid code")
    except Exception as e:
        print(f"2FA Enable Error: {e}")
        raise HTTPException(status_code=400, detail="Invalid token or secret error")

@router.post("/disable")
def disable_2fa(db: Session = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    username = Authorize.get_jwt_subject()
    user = db.query(User).filter(User.username == username).first()

    user.is_2fa_enabled = False
    user.otp_secret = None
    db.commit()
    return {"message": "2FA disabled successfully"}
