from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import StaticPool
from sqlalchemy.engine import make_url
from api.settings import get_settings
settings = get_settings()


# Translate DB URL for async drivers
database_url = make_url(get_settings().DATABASE_URL)
async_drivers = {"sqlite": "sqlite+aiosqlite", "postgresql": "postgresql+asyncpg", "postgres": "postgresql+asyncpg", "mysql": "mysql+aiomysql"}
db_url = database_url.set(drivername=async_drivers.get(database_url.get_backend_name(), database_url.drivername)).render_as_string(hide_password=False)

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


def sync_migration_url(database_url: str) -> str:
    """Use installed synchronous drivers for Alembic's migration engine."""
    url = make_url(database_url)
    drivers = {
        "sqlite+aiosqlite": "sqlite",
        "postgresql": "postgresql+psycopg2",
        "postgresql+asyncpg": "postgresql+psycopg2",
        "mysql": "mysql+pymysql",
        "mysql+aiomysql": "mysql+pymysql",
    }
    return url.set(drivername=drivers.get(url.drivername, url.drivername)).render_as_string(
        hide_password=False
    )

async def get_db():
    async with SessionLocal() as db:
        yield db
