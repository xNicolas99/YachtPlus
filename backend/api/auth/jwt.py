import jwt
import secrets as _secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from api.settings import Settings

settings = Settings()


async def _is_jti_revoked(jti: str) -> bool:
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
    try:
        async with SessionLocal() as db:
            row = await db.execute(
                select(TokenBlacklist).filter(TokenBlacklist.jti == jti)
            )
            row = row.scalars().first()
            return bool(row and row.revoked)
    except Exception:
        # The blacklist check is a secondary guard. If the DB is unavailable
        # or the table doesn't exist, do not fail the whole token validation
        # path — treat the token as not revoked so an outage doesn't lock
        # everyone out. (Real revocations are re-checked once the DB returns.)
        return False


async def revoke_token(token: str) -> None:
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
        datetime.fromtimestamp(exp_ts, tz=timezone.utc) if isinstance(exp_ts, (int, float)) else None
    )

    from api.db.database import SessionLocal
    from api.db.models.settings import TokenBlacklist
    async with SessionLocal() as db:
        try:
            # Prune expired blacklist entries opportunistically so the table
            # doesn't grow without bound — entries past their `expires` are
            # safe to drop since the JWT itself would fail `verify_exp` now.
            await db.execute(
                delete(TokenBlacklist).filter(
                    TokenBlacklist.expires.isnot(None),
                    TokenBlacklist.expires < datetime.now(timezone.utc),
                )
            )

            existing = await db.execute(
                select(TokenBlacklist).filter(TokenBlacklist.jti == jti)
            )
            existing = existing.scalars().first()
            if existing:
                existing.revoked = True
                existing.expires = expires_at
            else:
                db.add(TokenBlacklist(jti=jti, expires=expires_at, revoked=True))
            await db.commit()
        except Exception:
            await db.rollback()

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
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    # jti = unique per-token id so /logout can blacklist exactly THIS
    # token (and re-uses of an older JWT for the same user are not
    # accidentally invalidated). Without this, JWTs were stateless and
    # remained valid until `exp` even after the user logged out.
    to_encode.update({"exp": expire, "jti": _secrets.token_urlsafe(16)})
    encoded_jwt = jwt.encode(to_encode, get_secret_key(), algorithm=ALGORITHM)
    return encoded_jwt

async def verify_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        setup_pending: bool = payload.get("setup_pending", False)
        if username is None:
            raise credentials_exception
        if await _is_jti_revoked(payload.get("jti")):
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

async def get_current_user(token: str = Depends(get_current_user_token)):
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

    return await verify_token(token, credentials_exception)

class AuthWrapper:
    def __init__(self, request: Request):
        self.request = request
        self.user = None

    async def jwt_required(self, allow_setup_pending: bool = False):
        token = get_current_user_token(self.request)
        token_data = await get_current_user(token)

        # Enforce setup_pending logic here
        if isinstance(token_data, TokenData) and token_data.setup_pending and not allow_setup_pending:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Setup is pending, restricted access"
            )

        self.user = token_data
        return self.user

    async def get_jwt_subject(self, allow_setup_pending: bool = False):
        if self.user:
            return self.user.username
        # If jwt_required wasn't called (it should have been), call it
        user = await self.jwt_required(allow_setup_pending=allow_setup_pending)
        return user.username

    def unset_jwt_cookies(self, response):
        # path must match the one used in set_access_cookies, else the
        # browser keeps the original cookie around (silent /logout no-op).
        response.delete_cookie("access_token_cookie", path="/")

    def _resolve_secure_flag(self) -> bool:
        """Decide whether to mark the access-token cookie Secure.

        Three cases:
          - settings.SECURE_COOKIES is True  -> always Secure (admin opted in).
          - settings.SECURE_COOKIES is False -> never Secure (admin opted out).
          - settings.SECURE_COOKIES is None  -> auto: Secure only if THIS
            request is HTTPS. We check the URL scheme first; behind nginx
            that's always http://, so we also honour X-Forwarded-Proto.
            (X-Forwarded-Proto is set by *our own* nginx in nginx.conf, so
            trusting it here is safe — a remote attacker can't reach the
            gunicorn worker except through that proxy.)

        Without this auto-detect the LAN/HTTP setup flow was unrecoverable:
        the browser refused the Secure cookie over http://192.168.x.y and
        every subsequent /2fa/* call returned 401.
        """
        explicit = settings.SECURE_COOKIES
        if explicit is True:
            return True
        if explicit is False:
            return False
        scheme = (self.request.url.scheme or "").lower()
        if scheme == "https":
            return True
        forwarded_proto = self.request.headers.get("x-forwarded-proto", "")
        # The header can be a comma-separated list ("https, http") when
        # there are multiple proxies; the FIRST hop is the one closest
        # to the original client, which is what we care about.
        if forwarded_proto.split(",")[0].strip().lower() == "https":
            return True
        return False

    def set_access_cookies(self, token, response, max_age=None):
        response.set_cookie(
            key="access_token_cookie",
            value=token,
            httponly=True,
            max_age=max_age or int(settings.ACCESS_TOKEN_EXPIRES),
            samesite=settings.SAME_SITE_COOKIES,
            secure=self._resolve_secure_flag(),
            path="/",  # explicit so it's sent on every API path, not just /api/setup/*
        )

def get_auth_wrapper(request: Request):
    return AuthWrapper(request)
