import os
import secrets
from typing import Optional
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
    except Exception as e:
        # Refuse to start with an ephemeral per-process key. A random fallback
        # would invalidate all JWTs on every restart and diverge across workers.
        raise RuntimeError(
            f"SECRET_KEY could not be loaded or created at {secret_file!r}. "
            "Set the SECRET_KEY environment variable, or ensure SECRET_KEY_FILE "
            "points to a writable path."
        ) from e


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

    # Networking. The default list covers localhost only; for LAN deploys
    # set YACHT_ALLOWED_HOSTS to your hostname(s) or use the wildcard "*"
    # to disable Host-header pinning. ALLOW_PRIVATE_NETWORK_HOSTS=true (the
    # default) additionally accepts any RFC 1918 / link-local IP regardless
    # of this list — covers the "access via 192.168.x.y" case without
    # forcing every user to edit the env file. Set it to false to enforce
    # strict matching (typical for a public-internet deploy).
    ALLOWED_HOSTS: list = os.getenv("YACHT_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if os.getenv("YACHT_ALLOWED_HOSTS") else ["localhost", "127.0.0.1", "[::1]"]
    ALLOW_PRIVATE_NETWORK_HOSTS: bool = os.getenv("YACHT_ALLOW_PRIVATE_NETWORK_HOSTS", "true").lower() in ("1", "true", "yes", "on")
    CORS_ORIGINS: list = os.getenv("YACHT_CORS_ORIGINS", "http://localhost,http://127.0.0.1,http://localhost:8080,http://127.0.0.1:8080").split(",") if os.getenv("YACHT_CORS_ORIGINS") else ["http://localhost", "http://127.0.0.1", "http://localhost:8080", "http://127.0.0.1:8080"]

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:////config/yacht.db")

    # Directory where docker-compose project subdirectories live. Trailing
    # slash matters — every call site does `settings.COMPOSE_DIR + name`
    # and relies on it. Previously read but never declared, which crashed
    # with AttributeError under pydantic v2's extra='forbid'.
    COMPOSE_DIR: str = os.getenv("COMPOSE_DIR", "/compose/")

    # Docker daemon endpoint. None -> let the docker SDK / aiodocker pick up
    # the standard discovery (DOCKER_HOST env var, then /var/run/docker.sock).
    # Set this when fronting the daemon via a TCP proxy so that *all* code
    # paths — including the few sync helpers that previously called
    # docker.from_env() — go through the configured endpoint.
    DOCKER_HOST: Optional[str] = os.getenv("DOCKER_HOST")

    # Comma-separated list of reverse-proxy IPs (or CIDRs) whose
    # X-Real-IP / X-Forwarded-For headers we trust for client-IP attribution.
    # 127.0.0.1 is in the default because YachtPlus's own nginx sits in
    # front of gunicorn on the loopback — without it every request looks
    # like it's coming from 127.0.0.1, and one user's traffic burns the
    # rate-limit budget for everyone. To harden against header spoofing
    # from co-located containers etc., this list is *exclusive*: anything
    # NOT listed here will never have its X-Forwarded-For honoured.
    TRUSTED_PROXIES: list = (
        [p.strip() for p in os.getenv("YACHT_TRUSTED_PROXIES", "").split(",") if p.strip()]
        if os.getenv("YACHT_TRUSTED_PROXIES") is not None
        else ["127.0.0.1", "::1"]
    )

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
