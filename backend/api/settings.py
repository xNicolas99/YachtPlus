import os
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "insecure_secret_key_change_me")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    ACCESS_TOKEN_EXPIRES: int = 1440 * 60 # Legacy support

    # Auth & Cookies (Fixes for jwt.py/auth.py)
    DISABLE_AUTH: bool = False
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    # Erzwinge HTTPS-Cookies, wenn wir nicht in der Entwicklung sind
    SECURE_COOKIES: bool = os.getenv("SECURE_COOKIES", ENVIRONMENT == "production")
    SAME_SITE_COOKIES: str = "lax"

    # Networking
    ALLOWED_HOSTS: list = os.getenv("YACHT_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if os.getenv("YACHT_ALLOWED_HOSTS") else ["localhost", "127.0.0.1", "[::1]"]

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:////config/yacht.db")

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
