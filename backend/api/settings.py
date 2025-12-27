import os
import secrets
import json
import logging
from pydantic_settings import BaseSettings
from typing import List

basedir = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

def load_base_template_variables():
    try:
        with open(os.path.join(basedir, "db/base_template_variables.json"), "r") as f:
            return json.load(f)
    except Exception:
        return []

def compose_dir_check():
    if not os.environ.get("COMPOSE_DIR", "/config/compose/").endswith("/"):
        os.environ["COMPOSE_DIR"] += "/"
    return os.environ.get("COMPOSE_DIR", "/config/compose/")

def get_or_create_secret_key():
    """
    Get SECRET_KEY from env or generate one and persist it to a file
    so it survives restarts (if not provided via env).
    This replaces DB storage for secrets.
    """
    if os.environ.get("SECRET_KEY"):
        return os.environ.get("SECRET_KEY")

    # Check for secret file
    secret_file = "/config/secret.key"
    try:
        if os.path.exists(secret_file):
            with open(secret_file, "r") as f:
                key = f.read().strip()
                if key:
                    return key
    except Exception as e:
        logger.warning(f"Error reading secret key from {secret_file}: {e}")

    # Generate and save
    logger.info("Generating new SECRET_KEY...")
    key = secrets.token_hex(32)
    try:
        # Ensure /config exists (it should in container)
        if not os.path.exists("/config"):
            os.makedirs("/config", exist_ok=True)

        with open(secret_file, "w") as f:
            f.write(key)
        logger.info(f"SECRET_KEY persisted to {secret_file}")
    except Exception as e:
        # If we can't write, we just return the ephemeral key, but log CRITICAL
        logger.critical(f"Failed to write SECRET_KEY to {secret_file}. Encryption will fail on restart! Error: {e}")
        pass

    return key

class Settings(BaseSettings):
    app_name: str = "Yacht API"
    SECRET_KEY: str = get_or_create_secret_key()
    ADMIN_PASSWORD: str = os.environ.get("ADMIN_PASSWORD", "pass")
    ADMIN_EMAIL: str = os.environ.get("ADMIN_EMAIL", "admin@yachtplus")
    ACCESS_TOKEN_EXPIRES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRES", 3600)) # 1 Hour
    REFRESH_TOKEN_EXPIRES: int = int(os.environ.get("REFRESH_TOKEN_EXPIRES", 2592000)) # 30 Days
    SAME_SITE_COOKIES: str = os.environ.get("SAME_SITE_COOKIES", "lax")
    SECURE_COOKIES: bool = os.environ.get("SECURE_COOKIES", "False").lower() == "true"
    DISABLE_AUTH: bool = os.environ.get("DISABLE_AUTH", "False").lower() == "true"
    ALLOWED_HOSTS: List[str] = os.environ.get("ALLOWED_HOSTS", "*").split(",")
    # Allowing CORS origins.
    ALLOWED_ORIGINS: List[str] = os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:8080,http://127.0.0.1:8080,http://localhost:8000,http://127.0.0.1:8000,http://192.168.50.84:8080,http://192.168.50.84:8000,https://192.168.50.84:8080,https://192.168.50.84:8000"
    ).split(",")
    BASE_TEMPLATE_VARIABLES: list = load_base_template_variables()
    BASE_TEMPLATE: str = os.environ.get("BASE_TEMPLATE", "")
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL", "sqlite:////config/data.sqlite"
    )
    COMPOSE_DIR: str = os.environ.get("COMPOSE_DIR", "/config/compose/")
