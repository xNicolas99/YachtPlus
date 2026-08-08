from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
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

# Import ALL routers (Fixed 'settings' -> 'app_settings')
from api.routers import (
    apps, dashboard, templates, resources, compose,
    app_settings, users, auth_2fa, audit, registries,
    containers, smtp, watchtower, search, setup
)
from api.db.database import engine, Base
from api.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run DDL asynchronously on the async engine. `Base.metadata.create_all`
    # must go through `engine.run_sync` for an AsyncEngine — a direct
    # `bind=engine` call raises AttributeError ('AsyncEngine' has no
    # '_run_ddl_visitor'). This is the async-migration fix that unblocks app
    # import.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="YachtPlus API", lifespan=lifespan)

# --- GLOBAL ERROR HANDLING ---
# Unexpected exceptions are logged server-side with a trace id and returned
# to the client as a generic message (no stack traces / SQL / paths leak).
# Validation errors are sanitised so sensitive input (passwords, tokens) is
# never echoed back verbatim.
app.add_exception_handler(Exception, unhandled_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# --- ROBUST SETUP CHECK ---
from api.routers.setup.setup import is_setup_completed_async


@app.middleware("http")
async def check_setup_status(request: Request, call_next):
    path = request.url.path
    # Whitelist static assets and auth endpoints
    if (path.startswith("/api/auth") or path.startswith("/assets") or
        path.startswith("/img") or "/favicon.ico" in path or
        request.method == "OPTIONS"):
        return await call_next(request)

    # Check setup status using the router's logic (DB + File). We use a fresh
    # async session for the check to ensure we get the latest DB state. The
    # async DB access never blocks the event loop.
    from api.db.database import SessionLocal
    async with SessionLocal() as db:
        setup_complete = await is_setup_completed_async(db)

    if not setup_complete:
        # Allow access to setup endpoints
        if not path.startswith("/api/setup"):
             if path.startswith("/api"):
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
#   2. ALLOW_PRIVATE_NETWORK_HOSTS=true (default) -> accept any RFC 1918 /
#      link-local IP literal in addition to the configured list. This is
#      what unblocks the "I hit http://192.168.1.42:8000/" case without
#      forcing every user to edit ALLOWED_HOSTS.
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

if os.path.exists("../frontend/dist"):
    app.mount("/", StaticFiles(directory="../frontend/dist", html=True), name="static")
