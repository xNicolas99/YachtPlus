import os
import secrets
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from functools import lru_cache

from api.utils.deployment_mode import DeploymentMode, ConfigCheck, detect_deployment_mode


def get_or_create_secret_key() -> str:
    """Return the persistent signing key, creating it atomically if needed.

    Race-safety: if multiple workers start simultaneously and the secret file
    does not exist yet, O_EXCL guarantees that exactly one process creates the
    file. The loser(s) catch EEXIST and re-read the file written by the winner,
    so every worker converges on the same key without file locks or a shared
    cache. A fixed-length read caps the amount of data we ever load from disk.
    """
    # First check environment variable
    env_secret = os.getenv("SECRET_KEY")
    if env_secret:
        return env_secret

    secret_file = os.getenv("SECRET_KEY_FILE", "/config/.secret_key")

    # If the default /config path is used and /config does not exist (e.g.
    # running outside Docker), fall back to the current directory. We only
    # override the *default* path, never an explicitly set SECRET_KEY_FILE.
    if secret_file == "/config/.secret_key":
        config_dir = os.path.dirname(secret_file)
        if config_dir and not os.path.exists(config_dir):
            secret_file = ".secret_key"

    secret_path = os.path.dirname(secret_file) or "."
    os.makedirs(secret_path, exist_ok=True)

    def _read_secret() -> str:
        # Limit read to a sane size to avoid loading a corrupt/malicious file.
        with open(secret_file, "r") as f:
            return f.read(256).strip()

    try:
        # Fast path: secret already on disk.
        if os.path.exists(secret_file):
            return _read_secret()

        # 48 urlsafe characters => 36 bytes of raw entropy before base64url
        # encoding, which decodes to >= 32 bytes. This satisfies PyJWT's
        # InsecureKeyLengthWarning for HS256 and exceeds RFC 7518's minimum.
        new_secret = secrets.token_urlsafe(48) + "\n"

        # Atomic create: if another worker already created the file, EEXIST
        # tells us to re-read the winner's key instead of overwriting it.
        fd = os.open(secret_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, new_secret.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        return new_secret.strip()
    except FileExistsError:
        # Another process won the race; converge on its key.
        return _read_secret()
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
    # to disable Host-header pinning. ALLOW_PRIVATE_NETWORK_HOSTS=false (the
    # new default) enforces strict Host-header matching — this prevents
    # SSRF/Host-header injection against internal services. LAN users can
    # set YACHT_ALLOW_PRIVATE_NETWORK_HOSTS=true to restore the legacy
    # behaviour (covers the "access via 192.168.x.y" case without forcing
    # every user to edit the env file), but that should only be used behind
    # a trusted network boundary.
    ALLOWED_HOSTS: list = os.getenv("YACHT_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if os.getenv("YACHT_ALLOWED_HOSTS") else ["localhost", "127.0.0.1", "[::1]"]
    ALLOW_PRIVATE_NETWORK_HOSTS: bool = os.getenv("YACHT_ALLOW_PRIVATE_NETWORK_HOSTS", "false").lower() in ("1", "true", "yes", "on")
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

    # Deployment-mode detection runs once per cached Settings instance.
    # It only logs health checks; it never blocks startup.
    _mode: DeploymentMode = DeploymentMode.LOCAL
    _checks: List[ConfigCheck] = []

    def model_post_init(self, __context):
        super().model_post_init(__context)
        self._mode, self._checks = detect_deployment_mode(self)

    @property
    def MODE(self) -> DeploymentMode:
        return self._mode

    @property
    def CONFIG_CHECKS(self) -> List[ConfigCheck]:
        return self._checks

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
