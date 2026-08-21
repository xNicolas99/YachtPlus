from sqlalchemy.future import select
from fastapi import APIRouter, Depends, HTTPException, Body, Request, Response
from api.auth.jwt import get_auth_wrapper, create_access_token, revoke_token, get_current_user_token
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import logging
import asyncio

from api.db.crud.users import verify_password, normalize_username
from api.utils.auth import get_db
from api.auth.auth import auth_check
from api.settings import get_settings
settings = get_settings()
from api.db.crud import users as crud
from api.db.models import users as models
from api.db.schemas import users as schemas
from api.utils.security import check_ip_restriction, record_login_attempt, limiter
from api.utils.crypto import decrypt
import pyotp

router = APIRouter()
logger = logging.getLogger(__name__)

# Shared limiter from api.utils.security (TRUSTED_PROXIES-aware resolver,
# common state). key_func applies per real client, not per nginx loopback peer.

# Used to keep login response time roughly constant when the supplied username
# is unknown. bcrypt.checkpw still runs against this fixed digest, so an
# attacker can't distinguish "no such user" from "wrong password" via timing.
# This is NOT a real credential, decrypts to nothing, and is the only
# "hardcoded password" in the codebase. Tell static analysers explicitly.
# nosem: generic.secrets.security.detected-generic-secret.detected-generic-secret
# nosec: B105
_TIMING_DUMMY_BCRYPT_HASH = "$2b$12$EPB.k0Vz4T5lXl6uT9f9/eG0m7b7mG3aR4jPq4s0q3wY0r7U5/7qC"


async def _authenticate_user(
    db: AsyncSession,
    request: Request,
    user_data: schemas.UserLogin,
) -> models.User:
    """Shared credential + 2FA verification for login and login_cookie.

    Returns the active, authenticated user. Raises HTTPException on any
    failure. Records every attempt via record_login_attempt.
    """
    if not user_data.username:
        raise HTTPException(status_code=400, detail="Validation error: required field(s) missing or invalid")

    username = crud.normalize_username(user_data.username)
    if not username:
        raise HTTPException(status_code=400, detail="Validation error: required field(s) missing or invalid")

    client_ip = await check_ip_restriction(request, db, username)

    _user = await crud.get_user_by_name(db=db, username=username)

    hash_to_verify = _user.hashed_password if _user else _TIMING_DUMMY_BCRYPT_HASH
    is_valid_password = await crud.verify_password(user_data.password, hash_to_verify)

    if _user is None or not is_valid_password:
        await record_login_attempt(db, client_ip, username, False)
        logger.warning("Login failed for IP: %s - Reason: Invalid credentials", client_ip)
        raise HTTPException(status_code=400, detail="Validation error: required field(s) missing or invalid")

    if not _user.is_active:
        await record_login_attempt(db, client_ip, username, False)
        logger.warning("Login failed for IP: %s - Reason: User is inactive", client_ip)
        raise HTTPException(status_code=400, detail="User account is inactive. Setup may be incomplete.")

    if _user.is_2fa_enabled:
        if not user_data.otp_token:
            # Caller must return the 2fa_required response; we just verify
            # the user exists and password is correct.
            return _user

        try:
            secret = decrypt(_user.otp_secret)
            totp = pyotp.TOTP(secret)
            code_ok = totp.verify(user_data.otp_token)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("2FA Verify Error: %s", e)
            await record_login_attempt(db, client_ip, username, False)
            logger.warning("Login failed for IP: %s - Reason: 2FA Error", client_ip)
            raise HTTPException(status_code=400, detail="Validation error: required field(s) missing or invalid")

        if not code_ok:
            await record_login_attempt(db, client_ip, username, False)
            logger.warning("Login failed for IP: %s - Reason: Invalid 2FA code", client_ip)
            raise HTTPException(status_code=400, detail="Validation error: required field(s) missing or invalid")

    await record_login_attempt(db, client_ip, username, True)
    return _user


# Add list users endpoint for admin
@router.get("/users", response_model=List[schemas.User])
async def get_users(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    # Ensure only superuser can list users (or define a new permission perm_manage_users)
    username = await Authorize.get_jwt_subject()
    user = await crud.get_user_by_name(db, username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found or deleted")
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")

    return await crud.get_users(db, skip=skip, limit=limit)

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    username = await Authorize.get_jwt_subject()
    user = await crud.get_user_by_name(db, username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found or deleted")
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")

    user_to_delete = await crud.get_user(db, user_id)
    if not user_to_delete:
        raise HTTPException(status_code=404, detail="User not found")

    if user_to_delete.id == user.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot delete your own account.",
        )

    if user_to_delete.is_superuser:
        res = await db.execute(select(models.User).filter(models.User.is_superuser == True, models.User.id != user_to_delete.id))
        remaining_admins = len(res.scalars().all())
        if remaining_admins == 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the last administrator.",
            )

    await db.delete(user_to_delete)
    await db.commit()
    return {"message": "User deleted"}

@router.put("/users/{user_id}", response_model=schemas.User)
async def update_user_admin(
    user_id: int,
    user_update: schemas.UserUpdate,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    username = await Authorize.get_jwt_subject()
    current_user = await crud.get_user_by_name(db, username)
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found or deleted")
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")

    db_user = await crud.update_user_by_id(db, user_id, user_update)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    return db_user


@router.post("/create", response_model=schemas.User)
async def create_user(
    user: schemas.UserCreate,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    db: AsyncSession = Depends(get_db),
):
    await auth_check(Authorize)
    username = await Authorize.get_jwt_subject()
    creator = await crud.get_user_by_name(db, username)
    if not creator:
         raise HTTPException(status_code=401, detail="User not found or deleted")
    if not creator.is_superuser:
         raise HTTPException(status_code=403, detail="Not authorized to create users")

    db_user = await crud.get_user_by_name(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already in use")
    return await crud.create_user(db=db, user=user)

async def _perform_login(
    db: AsyncSession,
    request: Request,
    user_data: schemas.UserLogin,
):
    """Shared login flow for /login and /login_cookie.

    Returns a tuple (response_payload, access_token). access_token is None
    when 2FA is required; the caller decides whether to return it in the
    body (/login) or set it as an HttpOnly cookie (/login_cookie).
    """
    _user = await _authenticate_user(db, request, user_data)

    if _user.is_2fa_enabled and not user_data.otp_token:
        return {"login": "2fa_required", "username": _user.username}, None

    access_token = create_access_token(data={"sub": _user.username})
    return {"login": "successful", "username": _user.username}, access_token


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    user_data: schemas.UserLogin = Body(..., embed=False),
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    payload, access_token = await _perform_login(db, request, user_data)
    if access_token is not None:
        payload["access_token"] = access_token
    return payload


@router.post("/login_cookie")
@limiter.limit("5/minute")
async def login_cookie(
    request: Request,
    response: Response,
    user_data: schemas.UserLogin = Body(..., embed=False),
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    payload, access_token = await _perform_login(db, request, user_data)
    if access_token is not None:
        # Token lives only in the HttpOnly cookie. Echoing it in the body
        # would defeat the cookie strategy by making the JWT reachable to
        # any DOM XSS via response.data.access_token.
        Authorize.set_access_cookies(access_token, response)
    return payload


@router.post("/refresh")
@limiter.limit("20/minute")
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    # The previous implementation just round-tripped the JWT subject into a
    # new token without validating the underlying account. A user that had
    # been deactivated or deleted could keep refreshing until the original
    # token's `exp` ran out — defeating the point of /refresh as a way to
    # extend a session under continued admin control.
    await auth_check(Authorize)
    current_user = await Authorize.get_jwt_subject()
    if not current_user:
        raise HTTPException(status_code=401, detail="Not logged in.")

    user = await crud.get_user_by_name(db=db, username=current_user)
    if not user or not user.is_active:
        # Clear the cookie so the client stops sending a token we just
        # rejected; this also lets the frontend redirect to /login.
        Authorize.unset_jwt_cookies(response)
        raise HTTPException(status_code=401, detail="Account is inactive or removed.")

    new_access_token = create_access_token(data={"sub": current_user})
    Authorize.set_access_cookies(new_access_token, response)
    return {"refresh": "successful"}


@router.get("/api/keys", response_model=List[schemas.APIKEY])
async def get_api_keys(db: AsyncSession = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    await auth_check(Authorize)
    current_user = await Authorize.get_jwt_subject()
    if current_user is not None:
        user = await crud.get_user_by_name(db=db, username=current_user)
    else:
        raise HTTPException(status_code=401, detail="Not logged in.")
    return await crud.get_keys(user, db)


@router.post("/api/keys/new", response_model=schemas.DisplayAPIKEY)
@limiter.limit("5/minute")
async def create_api_key(
    request: Request,
    key: schemas.GenerateAPIKEY,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    # Rate-limited so a compromised session can't spam-mint API keys
    # (each one is a long-lived credential — 10 year exp via create_key).
    name = key.key_name
    await auth_check(Authorize)
    username = await Authorize.get_jwt_subject()
    if username is not None:
        user = await crud.get_user_by_name(db=db, username=username)
    else:
        raise HTTPException(status_code=401, detail="Not logged in.")
    return await crud.create_key(name, user, Authorize, db)


# DELETE is the correct verb for revoking an API key; the previous GET
# route was CSRF-triggerable via <img src=...> and could be cached by
@router.delete("/api/keys/{key_id}")
async def delete_api_key(
    key_id, db: AsyncSession = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    username = await Authorize.get_jwt_subject()
    requester = await crud.get_user_by_name(db=db, username=username) if username else None
    if not requester:
        raise HTTPException(status_code=401, detail="Not logged in.")
    return await crud.blacklist_api_key(key_id, db, requesting_user=requester)


@router.get("/me", response_model=schemas.User)
async def get_user(db: AsyncSession = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    await auth_check(Authorize)
    if get_settings().DISABLE_AUTH:
        # Previous code mutated the schemas.User CLASS object directly,
        # which AttributeErrors on Pydantic v2 model classes and bleeds
        # state across requests. Construct a real instance instead.
        return schemas.User(
            id=0,
            username="user",
            is_active=True,
            is_superuser=True,
            authDisabled=True,
        )
    else:
        await Authorize.jwt_required()
        current_user_name = await Authorize.get_jwt_subject()
        if current_user_name is not None:
            user = await crud.get_user_by_name(db=db, username=current_user_name)
            if not user:
                raise HTTPException(status_code=401, detail="User not found or deleted.")
            return user
        else:
            raise HTTPException(status_code=401, detail="Not logged in.")


@router.post("/me", response_model=schemas.User)
async def update_user(
    user: schemas.UserUpdate, # Updated schema
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    await auth_check(Authorize)
    current_user = await Authorize.get_jwt_subject()
    return await crud.update_user(db=db, user=user, current_user=current_user)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    db: AsyncSession = Depends(get_db),
):
    # Blacklist the token's jti so a copy of the cookie/bearer that's been
    # captured elsewhere (browser session restored from disk, leaked from
    # a debug tool, etc.) can't be replayed for the remainder of the exp
    # window. The cookie is also cleared, but stateless JWTs were the
    # whole pre-existing gap — without the blacklist, /logout was
    # effectively a frontend-only cosmetic clear.
    token = get_current_user_token(request)
    if token:
        await revoke_token(token)
    Authorize.unset_jwt_cookies(response)
    return {"msg": "Logout Successful"}


@router.post("/logout/refresh")
async def logout_refresh(
    request: Request,
    response: Response,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    db: AsyncSession = Depends(get_db),
):
    token = get_current_user_token(request)
    if token:
        await revoke_token(token)
    Authorize.unset_jwt_cookies(response)
    return {"msg": "Logout Successful"}
