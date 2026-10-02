import pytest
from fastapi import HTTPException
from api.db.models.users import User
from api.db.schemas.users import UserUpdate

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from api.db.database import Base
import pytest_asyncio

engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
TestingSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autocommit=False, autoflush=False)


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSessionLocal() as session:
        yield session


class MockAuth:
    def __init__(self, username):
        self.username = username

    async def jwt_required(self, allow_setup_pending=False):
        return True

    async def get_jwt_subject(self, allow_setup_pending=False):
        return self.username


@pytest.mark.asyncio
async def test_update_duplicate_username(db):
    from api.routers.users import update_user_admin

    u1 = User(username="admin", hashed_password="pw", is_superuser=True)
    u2 = User(username="user1", hashed_password="pw", is_superuser=False)
    u3 = User(username="user2", hashed_password="pw", is_superuser=False)
    db.add(u1)
    db.add(u2)
    db.add(u3)
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await update_user_admin(user_id=2, user_update=UserUpdate(username="user2"), db=db, Authorize=MockAuth("admin"))

    # Collision now returns 409 (Conflict), which is the semantically correct
    # HTTP status for a uniqueness violation; previously the IntegrityError
    # path collapsed everything into 400.
    assert exc.value.status_code == 409
    assert "Username already in use" in exc.value.detail
