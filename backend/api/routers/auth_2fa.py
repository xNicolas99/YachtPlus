from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from api.db.database import SessionLocal
from api.db.models.users import User
from api.auth.jwt import get_auth_wrapper
from api.auth.auth import auth_check
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

@router.post("/generate")
def generate_2fa(db: Session = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    username = Authorize.get_jwt_subject()
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
    provisioning_uri = totp.provisioning_uri(name=user.username, issuer_name="Yacht")

    img = qrcode.make(provisioning_uri)
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()

    # Return the raw secret to the user for manual entry if needed, but it's stored encrypted
    return {"secret": secret, "qr_code": f"data:image/png;base64,{img_str}"}

@router.post("/enable")
def enable_2fa(token: str = Body(..., embed=True), db: Session = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    username = Authorize.get_jwt_subject()
    user = db.query(User).filter(User.username == username).first()

    if not user or not user.otp_secret:
        raise HTTPException(status_code=400, detail="2FA setup not initiated")

    try:
        # Decrypt secret
        secret = decrypt(user.otp_secret)
        totp = pyotp.TOTP(secret)
        if totp.verify(token):
            user.is_2fa_enabled = True
            db.commit()
            return {"message": "2FA enabled successfully"}
        else:
            raise HTTPException(status_code=400, detail="Invalid token")
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
