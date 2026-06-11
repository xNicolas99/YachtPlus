from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from api.settings import get_settings

settings = get_settings()





# Use check_same_thread=False for SQLite
connect_args = {"check_same_thread": False} if get_settings().DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    get_settings().DATABASE_URL,
    connect_args=connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency to be used in other routers
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
