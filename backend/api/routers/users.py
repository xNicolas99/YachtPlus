from fastapi import APIRouter, Depends, HTTPException, Body, Request, Response
from api.auth.jwt import get_auth_wrapper, create_access_token
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from api.db.crud.users import verify_password
from api.utils.auth import get_db
from api.auth.auth import auth_check
from api.settings import Settings
from api.db.crud import users as crud
from api.db.models import users as models
from api.db.schemas import users as schemas
from api.utils.security import check_ip_restriction, record_login_attempt
from api.utils.crypto import decrypt
import pyotp
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
settings = Settings()
logger = logging.getLogger(__name__)

# Initialize limiter (ensure it matches the one in main.py)
limiter = Limiter(key_func=get_remote_address)

# Used to keep login response time roughly constant when the supplied username
# is unknown. bcrypt.checkpw still runs against this fixed digest, so an
# attacker can't distinguish "no such user" from "wrong password" via timing.
# This is NOT a real credential, decrypts to nothing, and is the only
# "hardcoded password" in the codebase. Tell static analysers explicitly.
# nosem: generic.secrets.security.detected-generic-secret.detected-generic-secret
# nosec: B105
_TIMING_DUMMY_BCRYPT_HASH = "$2b$12$EPB.k0Vz4T5lXl6uT9f9/eG0m7b7mG3aR4jPq4s0q3wY0r7U5/7qC"

# Add list users endpoint for admin
@router.get("/users", response_model=List[schemas.User])
def get_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    # Ensure only superuser can list users (or define a new permission perm_manage_users)
    username = Authorize.get_jwt_subject()
    user = crud.get_user_by_name(db, username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found or deleted")
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")

    return crud.get_users(db, skip=skip, limit=limit)

@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    username = Authorize.get_jwt_subject()
    user = crud.get_user_by_name(db, username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found or deleted")
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")

    user_to_delete = crud.get_user(db, user_id)
    if not user_to_delete:
        raise HTTPException(status_code=404, detail="User not found")

    if user_to_delete.id == user.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot delete your own account.",
        )

    if user_to_delete.is_superuser:
        remaining_admins = (
            db.query(models.User)
            .filter(models.User.is_superuser == True, models.User.id != user_to_delete.id)
            .count()
        )
        if remaining_admins == 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the last administrator.",
            )

    db.delete(user_to_delete)
    db.commit()
    return {"message": "User deleted"}

@router.put("/users/{user_id}", response_model=schemas.User)
def update_user_admin(
    user_id: int,
    user_update: schemas.UserUpdate,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    username = Authorize.get_jwt_subject()
    current_user = crud.get_user_by_name(db, username)
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found or deleted")
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")

    db_user = crud.update_user_by_id(db, user_id, user_update)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    return db_user


@router.post("/create", response_model=schemas.User)
def create_user(
    user: schemas.UserCreate,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    db: Session = Depends(get_db),
):
    auth_check(Authorize)
    username = Authorize.get_jwt_subject()
    creator = crud.get_user_by_name(db, username)
    if not creator:
         raise HTTPException(status_code=401, detail="User not found or deleted")
    if not creator.is_superuser:
         raise HTTPException(status_code=403, detail="Not authorized to create users")

    db_user = crud.get_user_by_name(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already in use")
    return crud.create_user(db=db, user=user)

@router.post("/login")
@limiter.limit("5/minute")
def login(
    request: Request,
    user_data: schemas.UserLogin = Body(..., embed=False),
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    # Security Check
    if not user_data.username:
        raise HTTPException(status_code=400, detail="Validation error: required field(s) missing or invalid")

    client_ip = check_ip_restriction(request, db, user_data.username)

    # Defensive check for casefold
    username_query = user_data.username
    if hasattr(username_query, 'casefold'):
        username_query = username_query.casefold()

    _user = (
        db.query(models.User)
        .filter(models.User.username == username_query)
        .first()
    )

    hash_to_verify = _user.hashed_password if _user else _TIMING_DUMMY_BCRYPT_HASH
    is_valid_password = crud.verify_password(user_data.password, hash_to_verify)

    if _user is not None and is_valid_password:
        if not _user.is_active:
            record_login_attempt(db, client_ip, user_data.username, False)
            logger.warning(f"Login failed for IP: {client_ip} - Reason: User is inactive")
            raise HTTPException(status_code=400, detail="User account is inactive. Setup may be incomplete.")

        # Check 2FA
        if _user.is_2fa_enabled:
            if not user_data.otp_token:
                return {
                    "login": "2fa_required",
                    "username": _user.username
                }
            else:
                # The previous implementation wrapped totp.verify() in a
                # broad `except Exception` that ALSO caught the legitimate
                # HTTPException(400) raised on a bad code — collapsing two
                # distinct failure modes into one ambiguous handler and
                # making it impossible to tell wrong-code from
                # crypto-corruption in production. Re-raise HTTPException
                # cleanly and only swallow real decrypt/parse errors.
                try:
                    secret = decrypt(_user.otp_secret)
                    totp = pyotp.TOTP(secret)
                    code_ok = totp.verify(user_data.otp_token)
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"2FA Verify Error: {e}")
                    record_login_attempt(db, client_ip, user_data.username, False)
                    logger.warning(f"Login failed for IP: {client_ip} - Reason: 2FA Error")
                    raise HTTPException(status_code=400, detail="Validation error: required field(s) missing or invalid")
                if not code_ok:
                    record_login_attempt(db, client_ip, user_data.username, False)
                    logger.warning(f"Login failed for IP: {client_ip} - Reason: Invalid 2FA code")
                    raise HTTPException(status_code=400, detail="Validation error: required field(s) missing or invalid")

        # Success
        record_login_attempt(db, client_ip, user_data.username, True)
        access_token = create_access_token(data={"sub": _user.username})

        return {
            "login": "successful",
            "username": _user.username,
            "access_token": access_token,
        }
    else:
        record_login_attempt(db, client_ip, user_data.username, False)
        logger.warning(f"Login failed for IP: {client_ip} - Reason: Invalid credentials")
        raise HTTPException(status_code=400, detail="Validation error: required field(s) missing or invalid")

@router.post("/login_cookie")
@limiter.limit("5/minute")
def login_cookie(
    request: Request,
    response: Response,
    user_data: schemas.UserLogin = Body(..., embed=False),
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    # Security Check
    if not user_data.username:
        raise HTTPException(status_code=400, detail="Validation error: required field(s) missing or invalid")

    client_ip = check_ip_restriction(request, db, user_data.username)

    # Defensive check for casefold
    username_query = user_data.username
    if hasattr(username_query, 'casefold'):
        username_query = username_query.casefold()

    _user = (
        db.query(models.User)
        .filter(models.User.username == username_query)
        .first()
    )

    hash_to_verify = _user.hashed_password if _user else _TIMING_DUMMY_BCRYPT_HASH
    is_valid_password = crud.verify_password(user_data.password, hash_to_verify)

    if _user is not None and is_valid_password:
        if not _user.is_active:
            record_login_attempt(db, client_ip, user_data.username, False)
            logger.warning(f"Login failed for IP: {client_ip} - Reason: User is inactive")
            raise HTTPException(status_code=400, detail="User account is inactive. Setup may be incomplete.")

        if _user.is_2fa_enabled:
             if not user_data.otp_token:
                return {"login": "2fa_required", "username": _user.username}

             try:
                 secret = decrypt(_user.otp_secret)
                 totp = pyotp.TOTP(secret)
                 code_ok = totp.verify(user_data.otp_token)
             except HTTPException:
                 raise
             except Exception as e:
                 logger.error(f"2FA Verify Error: {e}")
                 record_login_attempt(db, client_ip, user_data.username, False)
                 logger.warning(f"Login failed for IP: {client_ip} - Reason: 2FA Error")
                 raise HTTPException(status_code=400, detail="Validation error: required field(s) missing or invalid")
             if not code_ok:
                 record_login_attempt(db, client_ip, user_data.username, False)
                 logger.warning(f"Login failed for IP: {client_ip} - Reason: Invalid 2FA code")
                 raise HTTPException(status_code=400, detail="Validation error: required field(s) missing or invalid")

        record_login_attempt(db, client_ip, user_data.username, True)
        access_token = create_access_token(data={"sub": _user.username})
        Authorize.set_access_cookies(access_token, response)
        return {
            "login": "successful",
            "username": _user.username,
            "access_token": access_token,
        }
    else:
        record_login_attempt(db, client_ip, user_data.username, False)
        logger.warning(f"Login failed for IP: {client_ip} - Reason: Invalid credentials")
        raise HTTPException(status_code=400, detail="Validation error: required field(s) missing or invalid")


@router.post("/refresh")
@limiter.limit("20/minute")
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    # The previous implementation just round-tripped the JWT subject into a
    # new token without validating the underlying account. A user that had
    # been deactivated or deleted could keep refreshing until the original
    # token's `exp` ran out — defeating the point of /refresh as a way to
    # extend a session under continued admin control.
    auth_check(Authorize)
    current_user = Authorize.get_jwt_subject()
    if not current_user:
        raise HTTPException(status_code=401, detail="Not logged in.")

    user = crud.get_user_by_name(db=db, username=current_user)
    if not user or not user.is_active:
        # Clear the cookie so the client stops sending a token we just
        # rejected; this also lets the frontend redirect to /login.
        Authorize.unset_jwt_cookies(response)
        raise HTTPException(status_code=401, detail="Account is inactive or removed.")

    new_access_token = create_access_token(data={"sub": current_user})
    Authorize.set_access_cookies(new_access_token, response)
    return {"refresh": "successful", "access_token": new_access_token}


@router.get("/api/keys", response_model=List[schemas.APIKEY])
def get_api_keys(db: Session = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    current_user = Authorize.get_jwt_subject()
    if current_user is not None:
        user = crud.get_user_by_name(db=db, username=current_user)
    else:
        raise HTTPException(status_code=401, detail="Not logged in.")
    return crud.get_keys(user, db)


@router.post("/api/keys/new", response_model=schemas.DisplayAPIKEY)
@limiter.limit("5/minute")
def create_api_key(
    request: Request,
    key: schemas.GenerateAPIKEY,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    # Rate-limited so a compromised session can't spam-mint API keys
    # (each one is a long-lived credential — 10 year exp via create_key).
    name = key.key_name
    auth_check(Authorize)
    username = Authorize.get_jwt_subject()
    if username is not None:
        user = crud.get_user_by_name(db=db, username=username)
    else:
        raise HTTPException(status_code=401, detail="Not logged in.")
    return crud.create_key(name, user, Authorize, db)


# DELETE is the correct verb for revoking an API key; the previous GET
# route was CSRF-triggerable via <img src=...> and could be cached by
# intermediaries. The GET alias is retained for one release so existing
# frontend builds keep working — remove once clients are migrated.
@router.delete("/api/keys/{key_id}")
@router.get("/api/keys/{key_id}", deprecated=True)
def delete_api_key(
    key_id, db: Session = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    username = Authorize.get_jwt_subject()
    requester = crud.get_user_by_name(db=db, username=username) if username else None
    if not requester:
        raise HTTPException(status_code=401, detail="Not logged in.")
    return crud.blacklist_api_key(key_id, db, requesting_user=requester)


@router.get("/me", response_model=schemas.User)
def get_user(db: Session = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    auth_setting = str(settings.DISABLE_AUTH)
    if auth_setting.lower() == "true":
        current_user = schemas.User
        current_user.authDisabled = True
        current_user.id = 0
        current_user.username = "user"
        current_user.is_active = True
        current_user.is_superuser = True
        return current_user
    else:
        Authorize.jwt_required()
        current_user_name = Authorize.get_jwt_subject()
        if current_user_name is not None:
            user = crud.get_user_by_name(db=db, username=current_user_name)
            if not user:
                raise HTTPException(status_code=401, detail="User not found or deleted.")
            return user
        else:
            raise HTTPException(status_code=401, detail="Not logged in.")


@router.post("/me", response_model=schemas.User)
def update_user(
    user: schemas.UserUpdate, # Updated schema
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    auth_check(Authorize)
    current_user = Authorize.get_jwt_subject()
    return crud.update_user(db=db, user=user, current_user=current_user)


@router.get("/logout")
def logout(response: Response, Authorize: get_auth_wrapper = Depends(get_auth_wrapper), db: Session = Depends(get_db)):
    Authorize.unset_jwt_cookies(response)
    return {"msg": "Logout Successful"}


@router.get("/logout/refresh")
def logout_refresh(response: Response, Authorize: get_auth_wrapper = Depends(get_auth_wrapper), db: Session = Depends(get_db)):
    Authorize.unset_jwt_cookies(response)
    return {"msg": "Logout Successful"}
