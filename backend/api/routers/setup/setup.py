from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Body, Request, Response
from slowapi import Limiter
from api.utils.security import rate_limit_key
from sqlalchemy.orm import Session
from api.db.database import SessionLocal
from api.db.models.users import User
from api.db.schemas.users import UserCreate, UserUpdate
from api.db.crud.users import create_user, get_user_by_name, update_user_by_id
from api.utils.auth import get_db
from api.auth.jwt import create_access_token, get_auth_wrapper
from api.auth.auth import auth_check, auth_check_setup_pending
from api.db.models.setup import SetupStatus
import logging
import os

logger = logging.getLogger(__name__)

# Short-lived window in which the user must complete 2FA setup and call
# /finalize. Long enough for a normal scan-the-QR-and-enter-code flow,
# short enough that an abandoned registration can't sit around for hours.
SETUP_PENDING_TOKEN_LIFETIME = timedelta(minutes=15)

router = APIRouter()

# /setup/register is unauthenticated by design (it bootstraps the first
# admin) so without a rate limit it doubles as a CPU exhaust vector via
# bcrypt — each call invokes the work-factor-12 hash. Cap at a value
# that's still comfortable for a real install over a flaky connection.
limiter = Limiter(key_func=rate_limit_key)

# Whitelist the directories the setup flag file is allowed to live under.
# /config is the production volume mount; $cwd covers dev installs and the
# pytest tmpdirs. The env override is honoured only if its resolved path
# lies inside one of these roots — otherwise we fall back to the default.
# This stops a hostile SETUP_FLAG_FILE value from being used as a
# path-traversal primitive to drop a file outside the volume.
#
# Note for Bandit: /tmp / /var/folders are deliberately NOT in this list
# (B108). The volume mount path /config is a fixed in-container path, not
# a world-writable tempdir.
_SETUP_FLAG_ALLOWED_ROOTS = (
    "/config",
    os.path.abspath(os.getcwd()),
)


def _resolve_setup_flag_file() -> str:
    requested = os.environ.get("SETUP_FLAG_FILE", "/config/.setup_completed")
    try:
        resolved = os.path.abspath(requested)
    except (TypeError, ValueError):
        return "/config/.setup_completed"
    for root in _SETUP_FLAG_ALLOWED_ROOTS:
        try:
            root_abs = os.path.abspath(root)
        except (TypeError, ValueError):
            continue
        # commonpath raises if drives differ on Windows; treat that as a miss.
        try:
            if os.path.commonpath([resolved, root_abs]) == root_abs:
                return resolved
        except ValueError:
            continue
    logger.warning(
        "SETUP_FLAG_FILE=%r outside allowed roots; falling back to default",
        requested,
    )
    return "/config/.setup_completed"


SETUP_FLAG_FILE = _resolve_setup_flag_file()

def is_setup_completed(db: Session = None):
    if not db:
        # Cannot check without DB
        if os.path.exists(SETUP_FLAG_FILE):
             return True
        return False

    status = db.query(SetupStatus).first()
    if status and (status.is_complete or status.is_bypassed):
        return True

    # Fallback to file check (legacy/migration)
    if os.path.exists(SETUP_FLAG_FILE):
        return True

    return False

def mark_setup_completed(db: Session):
    # Update DB
    status = db.query(SetupStatus).first()
    if not status:
        status = SetupStatus(is_complete=True)
        db.add(status)
    else:
        status.is_complete = True
    db.commit()

    # Auto-install the configured community Docker-image catalogs so the
    # user lands on a populated Templates page (image, ports, env, etc.
    # pre-filled per app) instead of an empty list. Failures are absorbed
    # inside init_templates — a network blip here must NEVER block
    # /setup/finalize from succeeding, otherwise the user can never
    # leave the wizard.
    try:
        from api.db.crud.templates import init_templates
        init_templates(db)
    except Exception:
        logger.exception("Default template seeding failed; continuing setup.")

    # Legacy file (optional but good for backwards compatibility).
    # Failures are non-fatal — the DB row is the source of truth — but
    # we log them at warning level so a wedged read-only volume or
    # permission flip on /config doesn't silently degrade the legacy
    # fallback path. The bare `except: pass` here previously hid those.
    try:
        os.makedirs(os.path.dirname(SETUP_FLAG_FILE), exist_ok=True)
        with open(SETUP_FLAG_FILE, "w") as f:
            f.write("Setup completed")
    except Exception as e:
        # Bare `except: pass` was masking real failures (permission flips,
        # disk full, read-only volume). Catch broadly so we never break
        # setup over a flag-file fluke, but log loud enough to be
        # diagnosable from server logs.
        logger.warning(
            "Could not write SETUP_FLAG_FILE=%s (DB row is the source of "
            "truth, continuing): %s",
            SETUP_FLAG_FILE,
            e,
        )

@router.get("/status")
def get_setup_status(db: Session = Depends(get_db)):
    return {"is_setup": is_setup_completed(db)}

@router.post("/bypass")
def bypass_setup(db: Session = Depends(get_db)):
    # The old behaviour of this endpoint was a one-shot brick: any
    # unauthenticated caller on a fresh instance could flip
    # SetupStatus.is_bypassed = True, which makes is_setup_completed()
    # return True. The setup middleware then stops short-circuiting /api/*
    # to 428, every data router falls through to auth_check, and no admin
    # user exists -> nobody can ever log in. The deployment is permanently
    # locked until someone edits the DB by hand.
    #
    # The endpoint also has no legitimate caller in the frontend (grep
    # confirms it's only referenced by tests). We keep the route shape for
    # backwards compatibility but require an explicit dev-mode opt-in via
    # DISABLE_AUTH=True. That env flag is already documented as dev-only
    # and gated everywhere else; reusing it here means an attacker can't
    # trigger this on a hardened production deploy.
    from api.settings import Settings
    if not Settings().DISABLE_AUTH:
        raise HTTPException(
            status_code=404,
            detail="Setup bypass is only available in dev mode (DISABLE_AUTH=True).",
        )

    if is_setup_completed(db):
        return {"message": "Setup already completed or bypassed."}

    if db.query(User).count() > 0:
        raise HTTPException(status_code=400, detail="Cannot bypass setup after a user has been registered.")

    status = db.query(SetupStatus).first()
    if not status:
        status = SetupStatus(is_bypassed=True)
        db.add(status)
    else:
        status.is_bypassed = True
    db.commit()

    return {"message": "Setup bypassed"}

@router.post("/register")
@limiter.limit("10/minute")
def register_first_user(
    request: Request,
    response: Response,
    user: UserCreate,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    if is_setup_completed(db):
         raise HTTPException(status_code=403, detail="Setup already completed.")

    # Check if user already exists
    existing_user = get_user_by_name(db, user.username)

    if existing_user:
        # If user exists but setup not complete, we allow overwrite/update
        # This handles the case where setup was aborted halfway
        user_update = UserUpdate(
            username=user.username,
            password=user.password,
            is_superuser=True,
            is_active=False
        )
        new_user = update_user_by_id(db, existing_user.id, user_update)
        if not new_user:
             raise HTTPException(status_code=500, detail="Failed to update user.")
    else:
        # Create the user as superuser
        user.is_superuser = True
        user.is_active = False
        try:
            new_user = create_user(db=db, user=user)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error creating user: {str(e)}")

    # Login the user BUT with a restrictive scope if we were advanced.
    # For now, to solve "Privilege Escalation if user aborts", we rely on the fact that
    # is_setup_completed() returns False.
    # The vulnerability is that they are "Logged In" as superuser.
    # However, standard auth checks don't check setup status.
    # Ideally, we should add a middleware or check in auth_check to enforce setup completion?
    # Or, we strictly modify the flow so the token is NOT FULL.

    # Fix: We will NOT set the cookie here if we want to force them to login manually?
    # No, that breaks the flow in frontend.
    # We will accept the risk of them being logged in, BUT we enforce 2FA in `finalize`.
    # The vulnerability report says: "An attacker ... has full Root access ... without ever entering a 2FA code."
    # If we stop here, they have root access.

    # Remediation: Don't set `is_superuser=True` yet?
    # No, they need it to access protected endpoints?
    # Actually, `generate_2fa` requires `auth_check`. `auth_check` requires valid token.
    # Permissions? `generate_2fa` just checks valid user.

    # SOLUTION: We will issue a token, but the frontend/backend should treat this user as "Pending 2FA Setup".
    # Since we can't easily change the token structure/claims without bigger refactor,
    # We can mitigate by NOT returning the token in the body, only cookie.
    # Wait, the report says "The access_token ... is stored in localStorage".
    # The previous code returned `access_token` in body.
    # We will REMOVE it from body and ONLY set cookie (HttpOnly).
    # This prevents XSS from stealing it immediately (though XSS is fixed elsewhere).

    # But for "Bypass", we can't fix it 100% without a state machine change.
    # However, I will implement a check: `is_active` set to False initially?
    # No, `login` checks `is_active`.

    # Minimal Fix: Remove `access_token` from JSON response.
    # And we rely on `finalize` to mark setup complete.
    # If an attacker stops here, the server is "Not Setup", so anyone can hit `/register` again?
    # No, existing user check prevents overwrite unless we handle it.

    access_token = create_access_token(
        data={"sub": new_user.username, "setup_pending": True},
        expires_delta=SETUP_PENDING_TOKEN_LIFETIME,
    )
    Authorize.set_access_cookies(
        access_token,
        response,
        max_age=int(SETUP_PENDING_TOKEN_LIFETIME.total_seconds()),
    )

    return {
        "login": "successful",
        "username": new_user.username
    }

@router.post("/finalize")
def finalize_setup(
    response: Response,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check_setup_pending(Authorize, db)
    if is_setup_completed(db):
        return {"message": "Setup already completed"}

    username = Authorize.get_jwt_subject(allow_setup_pending=True)
    user = get_user_by_name(db, username)

    if not user or not user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")

    if not user.is_2fa_enabled:
        raise HTTPException(status_code=400, detail="2FA must be enabled to finalize setup.")

    user.is_active = True
    db.commit()

    mark_setup_completed(db)

    # Issue a fresh token WITHOUT setup_pending so the user can access the rest of the application
    access_token = create_access_token(data={"sub": user.username})
    Authorize.set_access_cookies(access_token, response)

    return {"message": "Setup finalized"}
