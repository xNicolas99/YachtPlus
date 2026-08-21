from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse
from contextlib import asynccontextmanager
import ipaddress
import os

from api.utils.error_handler import (
    unhandled_exception_handler,
    validation_exception_handler,
)
from api.utils.security import limiter

# Import ALL routers (Fixed 'settings' -> 'app_settings')
from api.routers import (
    apps, dashboard, templates, resources, compose,
    app_settings, users, auth_2fa, audit, registries,
    containers, smtp, watchtower, search, setup
)
from api.db.database import engine, Base
from api.settings import get_settings

from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run DDL asynchronously on the async engine. `Base.metadata.create_all`
    # must go through `engine.run_sync` for an AsyncEngine — a direct
    # `bind=engine` call raises AttributeError ('AsyncEngine' has no
    # '_run_ddl_visitor'). This is the async-migration fix that unblocks app
    # import.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Deployment-mode health check: log the derived mode and any config
    # warnings/errors once at startup. We intentionally do not refuse to
    # start — a misconfigured but reachable instance is more useful than one
    # that fails silently. (FND-501 / S7)
    _settings = get_settings()
    mode = _settings.MODE
    checks = _settings.CONFIG_CHECKS
    errors = [c for c in checks if c.severity.value == "error"]
    warnings = [c for c in checks if c.severity.value == "warning"]
    infos = [c for c in checks if c.severity.value == "info"]
    logger.info(
        "YachtPlus deployment mode: %s | checks: %d info, %d warnings, %d errors",
        mode.value, len(infos), len(warnings), len(errors),
    )
    for check in checks:
        log_fn = logger.error if check.severity.value == "error" else logger.warning
        if check.severity.value == "info":
            log_fn = logger.info
        log_fn("[%s] %s: %s (keys: %s)", check.severity.value.upper(), check.rule_id, check.message, ", ".join(check.config_keys))
    if errors:
        logger.warning(
            "YachtPlus is starting despite %d configuration error(s). Review the [S7/*] log entries above.",
            len(errors),
        )

    # Start the automatic compose-update scheduler. It is a background
    # scheduler that runs its jobs in a dedicated thread, so it is safe to
    # start from the async lifespan. The guard inside start_scheduler
    # prevents multiple workers (gunicorn -w 4) from each starting a scheduler.
    from api.services.watchtower import start_scheduler
    try:
        start_scheduler()
    except Exception as exc:
        logger.error("Failed to start watchtower scheduler: %s", exc, exc_info=True)

    yield

    # Shutdown the scheduler cleanly on application exit.
    from api.services.watchtower import stop_scheduler
    try:
        stop_scheduler()
    except Exception as exc:
        logger.error("Failed to stop watchtower scheduler: %s", exc, exc_info=True)


app = FastAPI(title="YachtPlus API", lifespan=lifespan)
app.state.limiter = limiter

from slowapi.middleware import SlowAPIMiddleware
app.add_middleware(SlowAPIMiddleware)

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- GLOBAL ERROR HANDLING ---
# Unexpected exceptions are logged server-side with a trace id and returned
# to the client as a generic message (no stack traces / SQL / paths leak).
# Validation errors are sanitised so sensitive input (passwords, tokens) is
# never echoed back verbatim.
app.add_exception_handler(Exception, unhandled_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# --- ROBUST SETUP CHECK ---
from api.routers.setup.setup import is_setup_completed_async


# In-memory cache used by check_setup_status. TTL is short (5s) so that the
# setup-finalize handshake updates promptly, but most requests avoid a fresh DB
# round-trip. The cache is keyed by a short time bucket, so concurrent workers
# still converge within one bucket.
import time
_setup_status_cache: dict[str, tuple[bool, float]] = {}
_SETUP_STATUS_TTL_SECONDS = 5


@app.middleware("http")
async def check_setup_status(request: Request, call_next):
    path = request.url.path

    # Only /api paths need setup enforcement. Static assets, the SPA, root,
    # and CORS preflight must be cheap and never blocked by DB state.
    if not path.startswith("/api") or request.method == "OPTIONS":
        return await call_next(request)

    # Auth endpoints and setup endpoints are always allowed.
    if path.startswith("/api/auth") or path.startswith("/api/setup"):
        return await call_next(request)

    # Cached short-lived setup check to avoid a fresh DB session for every
    # static-asset poll or dashboard refresh.
    now = time.monotonic()
    bucket = str(int(now) // _SETUP_STATUS_TTL_SECONDS)
    cached = _setup_status_cache.get(bucket)
    if cached is None or now - cached[1] > _SETUP_STATUS_TTL_SECONDS:
        from api.db.database import SessionLocal
        async with SessionLocal() as db:
            setup_complete = await is_setup_completed_async(db)
        _setup_status_cache.clear()
        _setup_status_cache[bucket] = (setup_complete, now)
    else:
        setup_complete = cached[0]

    if not setup_complete:
        return JSONResponse(status_code=428, content={"detail": "Setup required"})

    return await call_next(request)

_cors_origins = [o.strip() for o in get_settings().CORS_ORIGINS if o and o.strip()]
# Fail fast on a misconfiguration that would silently disable credentialed
# CORS requests at runtime: per the CORS spec, "*" is incompatible with
# allow_credentials=True, and any unspecified scheme/host is unusable as
# an origin.
if "*" in _cors_origins:
    raise RuntimeError(
        "CORS_ORIGINS contains '*', which is incompatible with allow_credentials=True. "
        "Set YACHT_CORS_ORIGINS to an explicit list of trusted origins."
    )
for _origin in _cors_origins:
    if not (_origin.startswith("http://") or _origin.startswith("https://")):
        raise RuntimeError(
            f"Invalid CORS origin {_origin!r}: must include scheme (http:// or https://)."
        )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Reject requests with Host headers that aren't in ALLOWED_HOSTS so the API
# can't be tricked into emitting absolute URLs (password resets etc.) under
# an attacker-controlled host. Two convenience escapes from the strict
# whitelist for the typical YachtPlus deployment (LAN / private network):
#
#   1. YACHT_ALLOWED_HOSTS="*"  -> disable host pinning entirely.
#   2. ALLOW_PRIVATE_NETWORK_HOSTS=true -> accept any RFC 1918 /
#      link-local IP literal in addition to the configured list. This is
#      what unblocks the "I hit http://192.168.1.42:8000/" case without
#      forcing every user to edit ALLOWED_HOSTS. The default is false, so
#      LAN access requires explicitly setting YACHT_ALLOW_PRIVATE_NETWORK_HOSTS=true.
_host_settings = get_settings()
_allowed_hosts_raw = list(_host_settings.ALLOWED_HOSTS)


def _host_allowed(host_header: str) -> bool:
    if not host_header:
        # An empty Host header is a protocol-level oddity; reject it.
        return False
    # Strip the port and any IPv6 brackets.
    hostname = host_header.split(":")[0].strip("[]").lower()
    if "*" in _allowed_hosts_raw:
        return True
    for allowed in _allowed_hosts_raw:
        allowed = allowed.strip().lower()
        if not allowed:
            continue
        if allowed == hostname:
            return True
        # Starlette-style suffix wildcards: "*.example.com".
        if allowed.startswith("*.") and hostname.endswith(allowed[1:]):
            return True
    if _host_settings.ALLOW_PRIVATE_NETWORK_HOSTS:
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            return False
        return ip.is_private or ip.is_loopback or ip.is_link_local
    return False


@app.middleware("http")
async def _trusted_host_middleware(request: Request, call_next):
    host_header = request.headers.get("host", "")
    if not _host_allowed(host_header):
        return PlainTextResponse("Invalid host header", status_code=400)
    return await call_next(request)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # CSP: keep `script-src 'self' 'unsafe-inline'` (no unsafe-eval — Vue 3
    # runtime doesn't need it). Tighten the rest now that the duplicate
    # CDN <link> for @mdi/font was removed: only Google Fonts is loaded
    # cross-origin, and only for CSS + font files. Without these
    # directives the default falls through to `default-src 'self'` for
    # newer browsers (good) but old configs were silently permissive.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "object-src 'none'; "
        "base-uri 'self';"
    )
    # Legacy clickjacking fallback for browsers without CSP frame-ancestors.
    response.headers["X-Frame-Options"] = "DENY"
    return response

# --- REGISTER ALL ROUTERS ---
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(apps.router, prefix="/api/apps", tags=["apps"])
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
app.include_router(resources.router, prefix="/api/resources", tags=["resources"])
app.include_router(compose.router, prefix="/api/compose", tags=["compose"])
app.include_router(registries.router, prefix="/api/registries", tags=["registries"])
app.include_router(containers.router, prefix="/api/containers", tags=["containers"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(watchtower.router, prefix="/api/watchtower", tags=["watchtower"])
# Settings group
app.include_router(users.router, prefix="/api/auth", tags=["auth"])
app.include_router(auth_2fa.router, prefix="/api/auth/2fa", tags=["2fa"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
app.include_router(app_settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(smtp.router, prefix="/api/settings/email", tags=["smtp"]) # Standard convention
app.include_router(setup.router, prefix="/api/setup", tags=["setup"])

# The SPA is served by nginx from /app in the container. FastAPI intentionally
# does not mount a static directory here, so API requests that fall through
# nginx return a 404 instead of accidentally serving stale build artefacts.
