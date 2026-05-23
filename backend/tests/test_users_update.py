import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.db.database import Base
from api.db.models.users import User

engine = create_engine('sqlite:///:memory:')
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)
db = SessionLocal()

from api.routers.users import update_user_admin
from api.db.schemas.users import UserUpdate
from fastapi import HTTPException

class MockAuth:
    def __init__(self, username):
        self.username = username
    def jwt_required(self, allow_setup_pending=False):
        return True
    def get_jwt_subject(self, allow_setup_pending=False):
        return self.username

def test_update_duplicate_username():
    u1 = User(username="admin", hashed_password="pw", is_superuser=True)
    u2 = User(username="user1", hashed_password="pw", is_superuser=False)
    u3 = User(username="user2", hashed_password="pw", is_superuser=False)
    db.add(u1)
    db.add(u2)
    db.add(u3)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        update_user_admin(user_id=2, user_update=UserUpdate(username="user2"), db=db, Authorize=MockAuth("admin"))

    # Collision now returns 409 (Conflict), which is the semantically correct
    # HTTP status for a uniqueness violation; previously the IntegrityError
    # path collapsed everything into 400.
    assert exc.value.status_code == 409
    assert "Username already in use" in exc.value.detail
