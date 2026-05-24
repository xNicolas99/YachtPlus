import jwt
import secrets as _secrets
from datetime import datetime, timedelta
from typing import Optional, Dict
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from api.settings import Settings

settings = Settings()


def _is_jti_revoked(jti: str) -> bool:
    """Return True if `jti` is in the JWT blacklist. Used by verify_token
    to refuse tokens that were explicitly revoked via /logout, even if
    they're still inside their `exp` window.
    """
    if not jti:
        return False
    # Lazy import to avoid the circular dependency between auth.jwt and
    # the DB layer at module import time.
    try:
        from api.db.database import SessionLocal
        from api.db.models.settings import TokenBlacklist
    except Exception:
        return False
    db = SessionLocal()
    try:
        row = db.query(TokenBlacklist).filter(TokenBlacklist.jti == jti).first()
        return bool(row and row.revoked)
    finally:
        db.close()


def revoke_token(token: str) -> None:
    """Insert the token's jti into the blacklist with the token's exp as
    its TTL. Called from /logout. Tolerates malformed / already-revoked
    tokens — the caller is asking us to forget the token, so anything
    short of "we wrote a row" should still leave the user logged out.
    """
    if not token:
        return
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_exp": False},  # may be expired by now; that's fine
        )
    except jwt.PyJWTError:
        return
    jti = payload.get("jti")
    if not jti:
        return
    exp_ts = payload.get("exp")
    expires_at = (
        datetime.utcfromtimestamp(exp_ts) if isinstance(exp_ts, (int, float)) else None
    )

    from api.db.database import SessionLocal
    from api.db.models.settings import TokenBlacklist
    db = SessionLocal()
    try:
        # Prune expired blacklist entries opportunistically so the table
        # doesn't grow without bound — entries past their `expires` are
        # safe to drop since the JWT itself would fail `verify_exp` now.
        db.query(TokenBlacklist).filter(
            TokenBlacklist.expires.isnot(None),
            TokenBlacklist.expires < datetime.utcnow(),
        ).delete(synchronize_session=False)

        existing = db.query(TokenBlacklist).filter(TokenBlacklist.jti == jti).first()
        if existing:
            existing.revoked = True
            existing.expires = expires_at
        else:
            db.add(TokenBlacklist(jti=jti, expires=expires_at, revoked=True))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

# Schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    setup_pending: bool = False
    # Add other claims if needed

# JWT Configuration
# _SECRET_KEY is now strictly from settings
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(settings.ACCESS_TOKEN_EXPIRES) / 60

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def get_secret_key():
    return settings.SECRET_KEY

# Deprecated/Removed: set_secret_key (secrets are immutable after startup now)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    # jti = unique per-token id so /logout can blacklist exactly THIS
    # token (and re-uses of an older JWT for the same user are not
    # accidentally invalidated). Without this, JWTs were stateless and
    # remained valid until `exp` even after the user logged out.
    to_encode.update({"exp": expire, "jti": _secrets.token_urlsafe(16)})
    encoded_jwt = jwt.encode(to_encode, get_secret_key(), algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        setup_pending: bool = payload.get("setup_pending", False)
        if username is None:
            raise credentials_exception
        if _is_jti_revoked(payload.get("jti")):
            # Token was explicitly invalidated via /logout. Treat exactly
            # like an expired token from the client's perspective.
            raise credentials_exception
        token_data = TokenData(username=username, setup_pending=setup_pending)
        return token_data
    except jwt.PyJWTError:
        raise credentials_exception

def get_current_user_token(request: Request):
    # Check header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ")[1]

    # Check cookie
    token = request.cookies.get("access_token_cookie")
    if token:
        return token
    return None

def get_current_user(token: str = Depends(get_current_user_token)):
    auth_setting = str(settings.DISABLE_AUTH)
    if auth_setting.lower() == "true":
        return "admin" # Mock user when auth disabled

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    return verify_token(token, credentials_exception)

class AuthWrapper:
    def __init__(self, request: Request):
        self.request = request
        self.user = None

    def jwt_required(self, allow_setup_pending: bool = False):
        token = get_current_user_token(self.request)
        token_data = get_current_user(token)

        # Enforce setup_pending logic here
        if isinstance(token_data, TokenData) and token_data.setup_pending and not allow_setup_pending:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Setup is pending, restricted access"
            )

        self.user = token_data
        return self.user

    def get_jwt_subject(self, allow_setup_pending: bool = False):
        if self.user:
            return self.user.username
        # If jwt_required wasn't called (it should have been), call it
        return self.jwt_required(allow_setup_pending=allow_setup_pending).username

    def unset_jwt_cookies(self, response):
        response.delete_cookie("access_token_cookie")

    def set_access_cookies(self, token, response, max_age=None):
        # We need to set the cookie.
        # Using settings from main.py / settings.py
        # Logic to enable/disable secure flag for LAN vs Prod
        response.set_cookie(
            key="access_token_cookie",
            value=token,
            httponly=True,
            max_age=max_age or int(settings.ACCESS_TOKEN_EXPIRES),
            samesite=settings.SAME_SITE_COOKIES,
            secure=settings.SECURE_COOKIES
        )

def get_auth_wrapper(request: Request):
    return AuthWrapper(request)
