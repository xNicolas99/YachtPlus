from fastapi import APIRouter, Depends, HTTPException, Body, Request, Response
from sqlalchemy.orm import Session
from api.db.database import SessionLocal
from api.db.models.users import User
from api.db.schemas.users import UserCreate
from api.db.crud.users import create_user
from api.utils.auth import get_db
from api.auth.jwt import create_access_token, get_auth_wrapper
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

    # Check if user already exists in DB (sanity check, though we don't rely on it for setup status)
    # If the file doesn't exist but users do, we might have an issue.
    # But the user asked to NOT depend on admin account existence.
    # However, if we try to create 'admin@yacht.local' and it already exists, it will fail.
    # So we should probably check if the username exists and error out if so,
    # OR we handle the constraint error.

    # Create the user as superuser
    user.is_superuser = True
    try:
        new_user = create_user(db=db, user=user)
    except Exception as e:
        # If user exists, we probably can't proceed with THIS user.
        # But we haven't marked setup as complete.
        raise HTTPException(status_code=400, detail=f"Error creating user: {str(e)}")

    # Mark setup as complete
    mark_setup_completed()

    # Login the user
    access_token = create_access_token(data={"sub": new_user.username})
    Authorize.set_access_cookies(access_token, response)

    return {
        "login": "successful",
        "username": new_user.username,
        "access_token": access_token
    }
