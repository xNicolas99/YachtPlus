from ..settings import Settings
from ..db.database import SessionLocal

settings = Settings()


async def get_db():
    async with SessionLocal() as db:
        yield db
