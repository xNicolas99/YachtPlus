import os
import secrets
from pydantic import Field
from pydantic_settings import BaseSettings
from functools import lru_cache


def get_or_create_secret_key() -> str:
    # First check environment variable
    env_secret = os.getenv("SECRET_KEY")
    if env_secret:
        return env_secret

    # Check persistent file or create it
    secret_file = os.getenv("SECRET_KEY_FILE", "/config/.secret_key")

    # If the directory doesn't exist (e.g. running outside docker), fall back to current directory
    config_dir = os.path.dirname(secret_file)
    if config_dir and not os.path.exists(config_dir):
        # Graceful fallback for local development
        secret_file = ".secret_key"

    try:
        if os.path.exists(secret_file):
            with open(secret_file, "r") as f:
                return f.read().strip()
        else:
            new_secret = secrets.token_urlsafe(32)
            with open(secret_file, "w") as f:
                f.write(new_secret)
            return new_secret
    except Exception:
        # Fallback if file system is completely unwriteable
        return secrets.token_urlsafe(32)


class Settings(BaseSettings):
    # Security
    SECRET_KEY: str = Field(default_factory=get_or_create_secret_key)
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
    CORS_ORIGINS: list = os.getenv("YACHT_CORS_ORIGINS", "http://localhost,http://127.0.0.1,http://localhost:8080,http://127.0.0.1:8080").split(",") if os.getenv("YACHT_CORS_ORIGINS") else ["http://localhost", "http://127.0.0.1", "http://localhost:8080", "http://127.0.0.1:8080"]

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:////config/yacht.db")

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
