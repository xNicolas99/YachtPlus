import bcrypt
import asyncio
import hashlib
import jwt as _pyjwt
import secrets

from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from sqlalchemy.orm import selectinload
from sqlalchemy import func

from api.db.models import users as models
from api.db.models.settings import TokenBlacklist
from api.db.schemas import users as schemas
from api.auth.jwt import create_access_token, account_claims
from fastapi.exceptions import HTTPException


async def get_user(db: AsyncSession, user_id: int):
    result = await db.execute(select(models.User).filter(models.User.id == user_id).execution_options(populate_existing=True))
    return result.scalars().first()

async def get_user_by_name(db: AsyncSession, username: str):
    if not username:
        return None
    canonical = normalize_username(username)
    result = await db.execute(select(models.User).filter(models.User.username == canonical))
    return result.scalars().first()

async def get_users(db: AsyncSession, skip: int = 0, limit: int = 100):
    result = await db.execute(select(models.User).offset(skip).limit(limit))
    return result.scalars().all()

def normalize_username(username: str) -> str:
    if username is None:
        return ""
    return username.strip().casefold()

async def _username_is_taken(db: AsyncSession, username: str, excluding_id: int = None) -> bool:
    canonical = normalize_username(username)
    q = select(models.User).filter(func.lower(models.User.username) == canonical)
    if excluding_id is not None:
        q = q.filter(models.User.id != excluding_id)
    result = await db.execute(q)
    return result.scalars().first() is not None

async def create_user(db: AsyncSession, user: schemas.UserCreate):
    _hashed_password = await get_password_hash(user.password)
    canonical_username = normalize_username(user.username)

    if await _username_is_taken(db, canonical_username):
        raise HTTPException(status_code=409, detail="Username already in use.")

    db_user = models.User(
        username=canonical_username,
        hashed_password=_hashed_password,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        perm_start=user.perm_start,
        perm_stop=user.perm_stop,
        perm_restart=user.perm_restart,
        perm_delete=user.perm_delete,
    )
    db.add(db_user)
    try:
        await db.commit()
        await db.refresh(db_user)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Username already in use or database error")
    return db_user

async def update_user(db: AsyncSession, user: schemas.UserSelfUpdate, current_user: str):
    _user = await get_user_by_name(db=db, username=current_user)

    if not _user:
        raise HTTPException(status_code=404, detail="User not found.")
    if not _user.is_active:
        raise HTTPException(status_code=403, detail="User account is disabled.")
    if user.password or (user.username and normalize_username(user.username) != _user.username):
        if not user.current_password or not await verify_password(user.current_password, _user.hashed_password):
            raise HTTPException(400, "Current password is incorrect")
    _hashed_password = await get_password_hash(user.password) if user.password else None

    if user.username:
        canonical_username = normalize_username(user.username)
        if await _username_is_taken(db, canonical_username, excluding_id=_user.id):
            raise HTTPException(status_code=409, detail="Username already in use.")
        _user.username = canonical_username

    if _hashed_password:
        _user.hashed_password = _hashed_password
    if _hashed_password or user.username:
        _user.auth_version = secrets.token_hex(32)

    try:
        await db.commit()
        await db.refresh(_user)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Database update failed")
    return _user

async def _lock_admins(db):
    # Acquire a database write lock before counting administrators. This also
    # serializes SQLite writers and is shared by edit and delete transactions.
    await db.execute(update(models.User).where(models.User.is_superuser.is_(True)).values(roles=models.User.roles))


async def _guard_last_admin(db, db_user):
    if db_user.is_superuser and db_user.is_active:
        remaining = (await db.execute(select(func.count()).select_from(models.User).where(
            models.User.is_superuser.is_(True), models.User.is_active.is_(True), models.User.id != db_user.id
        ))).scalar()
        if not remaining:
            await db.rollback()
            raise HTTPException(400, "Cannot remove or disable the last administrator")


async def update_user_by_id(db: AsyncSession, user_id: int, user_update: schemas.UserUpdate, requesting_user_id=None):
    await _lock_admins(db)
    db_user = await get_user(db, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    if user_update.is_active is False or user_update.is_superuser is False:
        if db_user.id == requesting_user_id:
            await db.rollback()
            raise HTTPException(400, "You cannot disable or demote your own account")
        await _guard_last_admin(db, db_user)

    if user_update.username:
        canonical_username = normalize_username(user_update.username)
        if await _username_is_taken(db, canonical_username, excluding_id=db_user.id):
            raise HTTPException(status_code=409, detail="Username already in use.")
        db_user.username = canonical_username

    if user_update.password:
        db_user.hashed_password = await get_password_hash(user_update.password)

    if user_update.is_active is not None:
        db_user.is_active = user_update.is_active
    if user_update.is_superuser is not None:
        db_user.is_superuser = user_update.is_superuser
    if user_update.perm_start is not None:
        db_user.perm_start = user_update.perm_start
    if user_update.perm_stop is not None:
        db_user.perm_stop = user_update.perm_stop
    if user_update.perm_restart is not None:
        db_user.perm_restart = user_update.perm_restart
    if user_update.perm_delete is not None:
        db_user.perm_delete = user_update.perm_delete
    db_user.auth_version = secrets.token_hex(32)

    try:
        await db.commit()
        await db.refresh(db_user)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Username already in use or database error")
    return db_user

async def delete_user(db: AsyncSession, user_id: int):
    await _lock_admins(db)
    db_user = await get_user(db, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    await _guard_last_admin(db, db_user)
    keys = (await db.execute(select(models.APIKEY).where(models.APIKEY.user == user_id))).scalars().all()
    for key in keys:
        await _blacklist_key(db, key)
    await db.delete(db_user)
    await db.commit()
    return db_user

async def verify_password(plain_password, hashed_password):
    if isinstance(plain_password, str):
        plain_password = plain_password.encode('utf-8')
    if isinstance(hashed_password, str):
        hashed_password = hashed_password.encode('utf-8')
    return await asyncio.to_thread(bcrypt.checkpw, plain_password, hashed_password)

async def get_password_hash(password) -> str:
    """Hash a password with bcrypt without blocking the event loop.

    Uses 13 rounds to stay ahead of offline brute-force hardware in 2026.
    The previous default (bcrypt.gensalt() = 12 rounds) is still acceptable,
    but 13 provides a meaningful cost increase for little UX impact.
    """
    if isinstance(password, str):
        password = password.encode('utf-8')
    if len(password) > 72:
        raise HTTPException(
            status_code=422,
            detail="Password must be at most 72 bytes when UTF-8 encoded",
        )
    hashed = await asyncio.to_thread(bcrypt.hashpw, password, bcrypt.gensalt(rounds=13))
    return hashed.decode('utf-8')

async def prune_blacklist(db: AsyncSession):
    await db.execute(delete(TokenBlacklist).filter(TokenBlacklist.expires < datetime.now(timezone.utc)))
    await db.commit()
    return

async def blacklist_api_key(key_id, db: AsyncSession, requesting_user=None):
    from fastapi import HTTPException

    res = await db.execute(select(models.APIKEY).filter(models.APIKEY.id == key_id))
    key = res.scalars().first()
    if not key:
        # Raise 404 instead of returning a 200-shaped error dict. The
        # router is responsible for surfacing this as a proper HTTP 404.
        raise HTTPException(status_code=404, detail="Key not found")

    if requesting_user is not None:
        is_owner = key.user == requesting_user.id
        is_admin = getattr(requesting_user, 'is_superuser', False)
        if not (is_owner or is_admin):
            # Return the same status as a missing id (no IDOR id-existence
            # leak): a non-owner must not be able to tell whether the key
            # belongs to another account.
            raise HTTPException(status_code=404, detail="Key not found")

    # Hard-revoke the JWT: insert its jti into the blacklist so the token
    # becomes invalid immediately, even though it may have years of remaining
    # lifetime. Without this, deleting the APIKEY row only removes the lookup
    # record; the bearer token stays usable until exp.
    await _blacklist_key(db, key)

    await db.delete(key)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {"message": "Key deleted successfully."}


async def _blacklist_key(db, key):
    if key.jti:
        expires_at = key.expires
        # If we don't have a stored expiration, fall back to a far-future
        # timestamp (10 years from minting) so the row stays active long enough
        # to block the token.
        if expires_at is None:
            expires_at = datetime.now(timezone.utc) + timedelta(days=3650)
        existing = await db.get(TokenBlacklist, key.jti)
        if existing:
            existing.revoked = True
        else:
            db.add(TokenBlacklist(jti=key.jti, expires=expires_at, revoked=True))

async def get_keys(user, db: AsyncSession):
    res = await db.execute(select(models.APIKEY).filter(models.APIKEY.user == user.id))
    keys = res.scalars().all()
    return keys

async def create_key(key_name, user, Authorize, db: AsyncSession):
    if not user or not user.is_active:
        raise HTTPException(401, "Account is inactive or removed")
    api_key = create_access_token(
        data=account_claims(user, type="api_key"),
        expires_delta=timedelta(days=3650),
    )
    decoded = _pyjwt.decode(api_key, options={"verify_signature": False})
    jti = decoded.get("jti")
    expires_at = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)

    # Hash the key's unique JTI (not the bearer token). The JTI is a
    # high-entropy UUID embedded in the JWT; hashing it gives a stable,
    # unique lookup value without bcrypt's 72-byte input limit, which
    # would otherwise only cover the constant JWT header/payload prefix.
    _hashed_key = hashlib.sha256(jti.encode("utf-8")).hexdigest()

    db_key = models.APIKEY(
        key_name=key_name, user=user.id, hashed_key=_hashed_key, jti=jti, expires=expires_at
    )
    db.add(db_key)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(db_key)
    db_key.token = api_key
    return db_key.__dict__
