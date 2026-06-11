from api.settings import get_settings

settings = get_settings()
from ..db.database import SessionLocal




def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
