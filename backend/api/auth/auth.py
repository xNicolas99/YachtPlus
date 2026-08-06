from api.settings import Settings
from fastapi import HTTPException, Depends, status
from api.auth.jwt import get_auth_wrapper
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from api.db.models.users import User
from api.utils.auth import get_db

settings = Settings()

# This is a compatibility layer to replace fastapi-jwt-auth usage in other files
# The function `auth_check` was used in routers.
# Original signature: def auth_check(Authorize):
# Now Authorize will be our AuthWrapper.

async def auth_check(Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    if settings.DISABLE_AUTH is True:
        return
    else:
        # AuthWrapper.jwt_required() raises HTTPException if invalid
        await Authorize.jwt_required(allow_setup_pending=False)

async def auth_check_setup_pending(
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    db: AsyncSession = Depends(get_db),
):
    """Allow setup_pending=True tokens, but only while setup is genuinely incomplete.

    Once setup has been finalized, any still-valid setup_pending token is
    treated like a normal token and must satisfy the strict auth_check rules.
    Without this, a stale setup_pending token (15-min window) could still hit
    the 2FA endpoints after setup is done.
    """
    if settings.DISABLE_AUTH is True:
        return
    # Lazy import to avoid the circular dependency between auth.auth and the
    # setup router (which itself imports from this module).
    from api.routers.setup.setup import is_setup_completed_async
    if await is_setup_completed_async(db):
        await Authorize.jwt_required(allow_setup_pending=False)
    else:
        await Authorize.jwt_required(allow_setup_pending=True)

async def require_superuser(Authorize: get_auth_wrapper, db: AsyncSession) -> User:
    """Reject anyone who isn't an active superuser.

    Centralised gate for endpoints that mutate shared config (template
    variables, SMTP, audit log, settings import/export, host-level update)
    or read sensitive cross-tenant state (audit log).

    Returns the resolved User row so callers can audit/log without a second
    DB hit. Honours DISABLE_AUTH for dev mode parity with auth_check().
    """
    if settings.DISABLE_AUTH is True:
        # Return a transient (never persisted) User so callers that audit
        # `user.id` / `user.username` don't AttributeError on None in dev
        # mode. id=0 marks it as synthetic — no real row ever has id 0.
        return User(id=0, username="dev", is_active=True, is_superuser=True)
    await Authorize.jwt_required(allow_setup_pending=False)
    username = await Authorize.get_jwt_subject()
    if not username:
        raise HTTPException(status_code=401, detail="Not logged in.")
    result = await db.execute(select(User).filter(User.username == username))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or deleted")
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser required.")
    return user


async def check_permission(permission_name: str, Authorize: get_auth_wrapper, db: AsyncSession):
    """
    Checks if the current user has the specified permission.
    Admins (is_superuser) always have access.
    """
    if settings.DISABLE_AUTH is True:
        return True

    username = await Authorize.get_jwt_subject()
    result = await db.execute(select(User).filter(User.username == username))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if user.is_superuser:
        return True

    if getattr(user, permission_name, False):
        return True

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"User lacks permission: {permission_name}"
    )
