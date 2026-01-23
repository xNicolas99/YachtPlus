import os
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # App Settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "insecure_secret_key_change_me")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    # Compatibility alias for legacy code
    ACCESS_TOKEN_EXPIRES: int = 1440 * 60

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./config/yacht.db")

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
