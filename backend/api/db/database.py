from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import StaticPool
from api.settings import get_settings
settings = get_settings()


# Translate DB URL for async drivers. Match the prefixes exactly and only
# rewrite the plain (sync) form — a URL that already uses an async driver
# (e.g. `sqlite+aiosqlite:///...`) must pass through untouched. The previous
# substring `replace()` rewrote async URLs a second time and produced
# `sqlite+aiosqlite+aiosqlite:///...` (NoSuchModuleError at startup).
db_url = get_settings().DATABASE_URL
if db_url.startswith("sqlite:///"):
    db_url = "sqlite+aiosqlite:///" + db_url[len("sqlite:///"):]
elif db_url.startswith("postgresql://"):
    db_url = "postgresql+asyncpg://" + db_url[len("postgresql://"):]
elif db_url.startswith("mysql://"):
    db_url = "mysql+aiomysql://" + db_url[len("mysql://"):]

# SQLite needs StaticPool and specific connect_args for async testing
connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}
poolclass = StaticPool if "sqlite" in db_url else None

engine = create_async_engine(
    db_url,
    connect_args=connect_args,
    poolclass=poolclass,
    pool_pre_ping=True,
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
