from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from ..settings import Settings

settings = Settings()

SQLALCHEMY_DATABASE_URL = settings.SQLALCHEMY_DATABASE_URI

if "sqlite:///" in SQLALCHEMY_DATABASE_URL:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
