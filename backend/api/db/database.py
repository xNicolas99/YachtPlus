from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import StaticPool
from api.settings import get_settings
settings = get_settings()


# Translate DB URL for async drivers
db_url = get_settings().DATABASE_URL
if db_url.startswith("sqlite"):
    db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///")
elif db_url.startswith("postgresql"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
elif db_url.startswith("mysql"):
    db_url = db_url.replace("mysql://", "mysql+aiomysql://")

# SQLite needs StaticPool and specific connect_args for async testing
connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}
poolclass = StaticPool if "sqlite" in db_url else None

engine = create_async_engine(
    db_url,
    connect_args=connect_args,
    poolclass=poolclass
)

SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()

async def get_db():
    async with SessionLocal() as db:
        yield db
