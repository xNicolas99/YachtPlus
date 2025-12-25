import os
import secrets
import json
from pydantic_settings import BaseSettings
from typing import List

basedir = os.path.abspath(os.path.dirname(__file__))

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


class Settings(BaseSettings):
    app_name: str = "Yacht API"
    SECRET_KEY: str = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    ADMIN_PASSWORD: str = os.environ.get("ADMIN_PASSWORD", "pass")
    ADMIN_EMAIL: str = os.environ.get("ADMIN_EMAIL", "admin@yachtplus")
    ACCESS_TOKEN_EXPIRES: int = os.environ.get("ACCESS_TOKEN_EXPIRES", 3600) # 1 Hour
    REFRESH_TOKEN_EXPIRES: int = os.environ.get("REFRESH_TOKEN_EXPIRES", 2592000) # 30 Days
    SAME_SITE_COOKIES: str = os.environ.get("SAME_SITE_COOKIES", "lax")
    SECURE_COOKIES: bool = os.environ.get("SECURE_COOKIES", "False").lower() == "true"
    DISABLE_AUTH: bool = os.environ.get("DISABLE_AUTH", "False").lower() == "true"
    ALLOWED_HOSTS: List[str] = os.environ.get("ALLOWED_HOSTS", "*").split(",")
    # Allowing CORS origins. Default to common local dev ports and production via env.
    ALLOWED_ORIGINS: List[str] = os.environ.get("ALLOWED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080").split(",")
    BASE_TEMPLATE_VARIABLES: list = load_base_template_variables()
    BASE_TEMPLATE: str = os.environ.get("BASE_TEMPLATE", "")
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL", "sqlite:////config/data.sqlite"
    )
    COMPOSE_DIR: str = os.environ.get("COMPOSE_DIR", "/config/compose/")
