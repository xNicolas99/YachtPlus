import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.db.database import Base
from api.db.models.users import User

engine = create_engine('sqlite:///:memory:')
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)
db = SessionLocal()

from api.routers.users import get_users, delete_user, update_user_admin, create_user
from fastapi import HTTPException
from api.db.schemas.users import UserUpdate, UserCreate

class MockAuth:
    def __init__(self, username):
        self.username = username
    def jwt_required(self, allow_setup_pending=False):
        return True
    def get_jwt_subject(self, allow_setup_pending=False):
        return self.username

def test_deleted_user_access():
    auth = MockAuth("deleted_user")

    with pytest.raises(HTTPException) as exc1:
        get_users(db=db, Authorize=auth)
    assert exc1.value.status_code == 401

    with pytest.raises(HTTPException) as exc2:
        delete_user(user_id=1, db=db, Authorize=auth)
    assert exc2.value.status_code == 401

    with pytest.raises(HTTPException) as exc3:
        update_user_admin(user_id=1, user_update=UserUpdate(), db=db, Authorize=auth)
    assert exc3.value.status_code == 401

    with pytest.raises(HTTPException) as exc4:
        create_user(user=UserCreate(username="new", password="pw"), db=db, Authorize=auth)
    assert exc4.value.status_code == 401
