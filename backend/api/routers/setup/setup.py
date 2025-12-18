from fastapi import APIRouter, Depends, HTTPException, Body, Request, Response
from sqlalchemy.orm import Session
from api.db.database import SessionLocal
from api.db.models.users import User
from api.db.schemas.users import UserCreate, UserUpdate
from api.db.crud.users import create_user, get_user_by_name, update_user_by_id
from api.utils.auth import get_db
from api.auth.jwt import create_access_token, get_auth_wrapper
from api.auth.auth import auth_check
import os

router = APIRouter()

SETUP_FLAG_FILE = "/config/.setup_completed"

def is_setup_completed():
    return os.path.exists(SETUP_FLAG_FILE)

def mark_setup_completed():
    # Ensure directory exists
    os.makedirs(os.path.dirname(SETUP_FLAG_FILE), exist_ok=True)
    with open(SETUP_FLAG_FILE, "w") as f:
        f.write("Setup completed")

@router.get("/status")
def get_setup_status():
    return {"is_setup": is_setup_completed()}

@router.post("/register")
def register_first_user(
    response: Response,
    user: UserCreate,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    if is_setup_completed():
         raise HTTPException(status_code=403, detail="Setup already completed.")

    # Check if user already exists
    existing_user = get_user_by_name(db, user.username)

    if existing_user:
        if not existing_user.is_superuser:
             # Should not happen during setup unless DB is messy
             raise HTTPException(status_code=400, detail="User exists but is not admin.")

        # Update existing user credentials/state
        user_update = UserUpdate(
            username=user.username,
            password=user.password,
            is_superuser=True,
            is_active=True
        )
        new_user = update_user_by_id(db, existing_user.id, user_update)
        if not new_user:
             raise HTTPException(status_code=500, detail="Failed to update user.")
    else:
        # Create the user as superuser
        user.is_superuser = True
        try:
            new_user = create_user(db=db, user=user)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error creating user: {str(e)}")

    # DO NOT Mark setup as complete yet.
    # mark_setup_completed()

    # Login the user
    access_token = create_access_token(data={"sub": new_user.username})
    Authorize.set_access_cookies(access_token, response)

    return {
        "login": "successful",
        "username": new_user.username,
        "access_token": access_token
    }

@router.post("/finalize")
def finalize_setup(
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    if is_setup_completed():
        return {"message": "Setup already completed"}

    username = Authorize.get_jwt_subject()
    user = get_user_by_name(db, username)

    if not user or not user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")

    if not user.is_2fa_enabled:
        raise HTTPException(status_code=400, detail="2FA must be enabled to finalize setup.")

    mark_setup_completed()
    return {"message": "Setup finalized"}
