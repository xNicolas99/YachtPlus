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


from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from api.db.database import Base

engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession, expire_on_commit=False)

import pytest_asyncio
@pytest_asyncio.fixture
async def db_session():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSessionLocal() as session:
        yield session

class MockAuth:
    def __init__(self, username):
        self.username = username
    def jwt_required(self, allow_setup_pending=False):
        return True
    def get_jwt_subject(self, allow_setup_pending=False):
        return self.username

@pytest.mark.asyncio
async def test_deleted_user_access(db_session):
    auth = MockAuth("deleted_user")

    with pytest.raises(HTTPException) as exc1:
        await get_users(db=db_session, Authorize=auth)
    assert exc1.value.status_code == 401

    with pytest.raises(HTTPException) as exc2:
        await delete_user(user_id=1, db=db_session, Authorize=auth)
    assert exc2.value.status_code == 401

    with pytest.raises(HTTPException) as exc3:
        await update_user_admin(user_id=1, user_update=UserUpdate(username="foo"), db=db_session, Authorize=auth)
    assert exc3.value.status_code == 401

    with pytest.raises(HTTPException) as exc4:
        await create_user(user=UserCreate(username="foo", password="pw"), db=db_session, Authorize=auth)
    assert exc4.value.status_code == 401
    with pytest.raises(HTTPException) as exc1:
        await get_users(db=db_session, Authorize=auth)
    assert exc1.value.status_code == 401

    with pytest.raises(HTTPException) as exc2:
        await delete_user(user_id=1, db=db_session, Authorize=auth)
    assert exc2.value.status_code == 401

    with pytest.raises(HTTPException) as exc3:
        await update_user_admin(user_id=1, user_update=UserUpdate(), db=db_session, Authorize=auth)
    assert exc3.value.status_code == 401

    with pytest.raises(HTTPException) as exc4:
        await create_user(user=UserCreate(username="new", password="pw"), db=db_session, Authorize=auth)
    assert exc4.value.status_code == 401
