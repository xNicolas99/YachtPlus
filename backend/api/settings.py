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
    env_file = os.getenv("ENV_FILE", "/config/.env")

    # If the directory doesn't exist (e.g. running outside docker), fall back to current directory
    config_dir = os.path.dirname(env_file)
    if config_dir and not os.path.exists(config_dir):
        # Graceful fallback for local development
        env_file = ".env"
        secret_file = ".secret_key"

    try:
        # First try to read from .env
        if os.path.exists(env_file):
            with open(env_file, "r") as f:
                for line in f:
                    if line.startswith("SECRET_KEY="):
                        return line.split("=", 1)[1].strip()

        # If not found in .env, check legacy secret_file or generate new
        if os.path.exists(secret_file):
            with open(secret_file, "r") as f:
                new_secret = f.read().strip()
        else:
            # 48 urlsafe characters => 36 bytes of raw entropy before
            # base64url encoding, which decodes to >= 32 bytes. This satisfies
            # PyJWT's InsecureKeyLengthWarning for HS256 and gives a robust
            # margin beyond the 32-byte minimum recommended by RFC 7518.
            new_secret = secrets.token_urlsafe(48)

        # Write to .env
        with open(env_file, "a") as f:
            f.write(chr(10) + "SECRET_KEY=" + str(new_secret) + chr(10))

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
    # Tri-state. None (default) -> auto-detect per request: only mark the
    # cookie Secure when the request itself is HTTPS (or X-Forwarded-Proto
    # says so via a trusted proxy). This is what unblocks the LAN-over-HTTP
    # setup flow — the previous default of `ENVIRONMENT == "production"`
    # forced Secure=True even on plain http://192.168.x.y, which browsers
    # then rejected and the whole post-register / 2FA flow died with 401.
    # Set explicitly to True if you terminate TLS in front and want to be
    # extra strict, or to False to disable the Secure flag everywhere.
    SECURE_COOKIES: Optional[bool] = (
        None if os.getenv("SECURE_COOKIES") is None
        else os.getenv("SECURE_COOKIES").strip().lower() in ("1", "true", "yes", "on")
    )
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

    # Directory shipped *inside the image* with bundled catalog JSON
    # files (configs/*.json in the repo -> /api/configs/ in the container).
    # Loaded by init_templates() on first setup-finalize, so a fresh
    # install always has a populated Templates page — even fully offline.
    # Files matching *.json get one catalog entry each, titled from the
    # filename stem.
    BUILTIN_CATALOG_DIR: str = os.getenv("YACHT_BUILTIN_CATALOG_DIR", "/api/configs")

    # Community Docker-image catalogs the setup wizard auto-installs on
    # first finalize, so the user doesn't land on an empty Templates page
    # after install. Each entry is `Title|URL` (pipe-separated); comma
    # separates entries. Failures are non-fatal — a network blip during
    # setup must not block the user from finishing the wizard. Set
    # YACHT_DEFAULT_TEMPLATE_URLS="" to disable seeding entirely.
    DEFAULT_TEMPLATE_URLS: str = os.getenv(
        "YACHT_DEFAULT_TEMPLATE_URLS",
        # SelfhostedPro: ~300 curated self-hosted apps (Plex/Jellyfin/
        # Vaultwarden/Nextcloud/arr-stack/…); de-facto standard catalog
        # in this ecosystem.
        "SelfhostedPro|https://raw.githubusercontent.com/SelfhostedPro/selfhosted_templates/master/Template/portainer-v2.json,"
        # Portainer Community: ~100 entries, official Portainer format,
        # more conservative selection.
        "Portainer Community|https://raw.githubusercontent.com/portainer/templates/master/templates-2.0.json",
    )

    # Docker daemon endpoint. None -> let the docker SDK / aiodocker pick up
    # the standard discovery (DOCKER_HOST env var, then /var/run/docker.sock).
    # Set this when fronting the daemon via a TCP proxy so that *all* code
    # paths — including the few sync helpers that previously called
    # docker.from_env() — go through the configured endpoint.
    DOCKER_HOST: Optional[str] = os.getenv("DOCKER_HOST")

    # When true (default), login attempts from non-RFC1918 client IPs are
    # rejected outright. This protects the typical LAN/homelab deployment,
    # but makes any public-internet deployment (VPS behind TLS) impossible
    # to log into. Set YACHT_BLOCK_PUBLIC_IP_LOGIN=false for such deploys —
    # rate limiting, fail2ban counters and username lockout still apply.
    BLOCK_PUBLIC_IP_LOGIN: bool = os.getenv(
        "YACHT_BLOCK_PUBLIC_IP_LOGIN", "true"
    ).lower() in ("1", "true", "yes", "on")

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
