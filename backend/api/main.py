import logging
import uvicorn
import fcntl
import asyncio
import aiodocker
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from api.db.models.settings import TokenBlacklist
from api.settings import Settings
from api.utils.auth import get_db
from api.db.models.containers import TemplateVariables, Base
from api.db.models.settings import SecretKey
from api.db.database import SessionLocal, engine
from api.db.schemas.users import UserCreate
from api.db.crud.settings import generate_secret_key
from api.db.crud.users import create_user, get_users
from api.routers import apps, app_settings, compose, resources, templates, users, smtp, auth_2fa, watchtower, containers, dashboard, registries, search
from api.routers import setup
from api.db.crud.templates import read_template_variables, set_template_variables, get_templates, add_template
from api.db.models.containers import Template
from api.services.watchtower import start_scheduler, stop_scheduler
import docker.errors
import requests.exceptions

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = Settings()

if settings.DOCKER_HOST:
    logger.info(f"Using DOCKER_HOST: {settings.DOCKER_HOST}")
else:
    logger.info("Using default Docker socket (local).")

if settings.ALLOWED_HOSTS == ["*"]:
    logger.warning("CRITICAL SECURITY WARNING: ALLOWED_HOSTS is set to ['*']. This is insecure for production.")
    logger.warning("Please set ALLOWED_HOSTS to your specific domain or IP address in environment variables to prevent Host Header attacks.")

# Setup Rate Limiter
limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up...")

    # 1. Proxy Availability Check (Retry Logic)
    logger.info("Checking Docker Socket/Proxy availability...")
    docker_connected = False
    for i in range(5):
        try:
            docker_client = aiodocker.Docker(url=settings.DOCKER_HOST)
            await docker_client.version()
            await docker_client.close()
            docker_connected = True
            logger.info("Docker Socket/Proxy is available.")
            break
        except Exception as e:
            logger.warning(f"Docker connection attempt {i+1}/5 failed: {e}. Retrying in 2s...")
            await asyncio.sleep(2)

    if not docker_connected:
        logger.error("CRITICAL: Failed to connect to Docker after 5 attempts. Application may not function correctly.")

    Base.metadata.create_all(bind=engine)

    # 2. Scheduler Locking (Concurrency Control)
    scheduler_lock_file = "/tmp/yacht_scheduler.lock"
    scheduler_lock_fp = open(scheduler_lock_file, "w")
    try:
        # Try to acquire an exclusive non-blocking lock
        fcntl.lockf(scheduler_lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        logger.info("Scheduler Lock acquired. Starting Scheduler...")
        start_scheduler()
        app.state.scheduler_started_by_me = True
    except IOError:
        logger.info("Scheduler Lock already held by another worker. Skipping Scheduler start.")
        app.state.scheduler_started_by_me = False

    # Initialize App State
    try:
        db = SessionLocal()
        # Secret Key is now handled in settings.py (immutable env or file)
        # We no longer read/write it to DB here.

        users_exist = get_users(db=db)
        logger.info(f"DISABLE_AUTH = {settings.DISABLE_AUTH}")

        if users_exist:
            logger.info("Users Exist")

        template_variables_exist = read_template_variables(db)
        if template_variables_exist:
            logger.info("Template Variables Exist")
        else:
            logger.info("No Variables yet! Initializing defaults.")
            t_vars = settings.BASE_TEMPLATE_VARIABLES
            t_var_list = []
            for t in t_vars:
                template_variables = TemplateVariables(
                    variable=t.get("variable"), replacement=t.get("replacement")
                )
                t_var_list.append(template_variables)
            set_template_variables(new_variables=t_var_list, db=db)

        # Check for Default Template
        templates_exist = get_templates(db)
        if not templates_exist:
            logger.info("No templates found. Adding default SelfhostedPro template.")
            default_template = Template(
                title="SelfhostedPro Templates",
                url="https://raw.githubusercontent.com/SelfhostedPro/selfhosted_templates/master/Template/template.json"
            )
            add_template(db, default_template)

        db.close()
    except Exception as e:
        logger.error(f"Startup Initialization Error: {e}")
        # Consider re-raising if critical

    yield

    # Shutdown
    logger.info("Shutting down...")

    # Only stop scheduler if we started it
    if getattr(app.state, "scheduler_started_by_me", False):
        logger.info("Stopping Scheduler (I hold the lock)...")
        stop_scheduler()
        # Lock is released when file descriptor is closed or process exits
        # Explicitly closing file is good practice, though OS cleans up locks on process exit
        try:
            scheduler_lock_fp.close()
        except Exception:
            pass

app = FastAPI(root_path="/api", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middleware
# Handle CORS: If "*" is present in allowed origins, we must use allow_origin_regex
# to avoid the "AssertionError: Allowed origins cannot be set to ['*'] when allow_credentials=True"
allow_origins = settings.ALLOWED_ORIGINS
allow_origin_regex = None

if "*" in allow_origins:
    allow_origins = []
    allow_origin_regex = ".*"

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

@app.middleware("http")
async def check_setup_status(request: Request, call_next):
    """
    Middleware to enforce setup flow.
    If setup is not complete, access is restricted to setup-related endpoints.
    """
    if settings.DISABLE_AUTH is True:
        return await call_next(request)

    # Use a helper or import from setup module. Since circular imports are risky,
    # we replicate the check or import locally.
    from api.routers.setup.setup import is_setup_completed

    if not is_setup_completed():
        path = request.url.path

        # Normalize path: If it starts with /api/, strip it to match our router definitions
        # This handles cases where Nginx doesn't strip it, or local dev mode
        if path.startswith("/api/"):
            path = path[4:] # Remove /api prefix

        # Allow setup endpoints, static files (if any served by this app, though nginx handles them usually),
        # and auth endpoints required for setup (like login/token generation).
        # We also need to allow /api/settings/theme probably if used during setup?

        # FIX: The Nginx proxy strips '/api' from the path, so FastAPI sees '/setup/status' instead of '/api/setup/status'.
        # We must allow paths relative to the FastAPI root.
        allowed_prefixes = [
            "/setup",
            "/auth/login", # Need to login to finalize
            "/auth/jwt/login", # Alternate login
            "/auth/2fa", # 2FA setup
            "/auth/logout",
            "/auth/users", # Check if users exist (trigger setup wizard)
            "/settings", # Theme, version, and other non-sensitive settings needed for UI init
            "/manifest.json", # PWA manifest
            "/docs", "/openapi.json", "/redoc" # Allow docs for debugging? Maybe restrict in strict mode.
        ]

        # Check if path starts with any allowed prefix
        if not any(path.startswith(prefix) for prefix in allowed_prefixes):
            return JSONResponse(
                status_code=403,
                content={"detail": "Setup not completed. Access restricted to setup endpoints."}
            )

    response = await call_next(request)
    return response

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # 63072000 seconds = 2 years. Preload enabled.
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"

    # CSP: Mitigate XSS risks.
    # We allow 'unsafe-inline' for styles because Vuetify 3 uses them.
    # We have removed 'unsafe-eval' as we have migrated to Vue 3 + Vite (Runtime only).
    csp_policy = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data: https:; "
        "connect-src 'self' ws: wss: https:; "
        "frame-src 'none'; "
        "object-src 'none';"
    )
    response.headers["Content-Security-Policy"] = csp_policy
    return response


@app.exception_handler(docker.errors.DockerException)
async def docker_exception_handler(request: Request, exc: docker.errors.DockerException):
    """
    Handle Docker exceptions gracefully, specifically targeting connection errors
    likely caused by missing socket mounts or permission issues.
    """
    error_str = str(exc)
    logger.error(f"Docker Exception: {error_str}")

    # Permission Denied (e.g. user not in docker group)
    if "Permission denied" in error_str or "PermissionError" in error_str:
         return JSONResponse(
            status_code=503,
            content={
                "detail": "Permission denied while accessing Docker socket. Please ensure the container runs with correct permissions (e.g. DOCKER_GID).",
                "original_error": error_str
            },
        )

    # Missing Socket or Connection Refused
    if "Connection refused" in error_str or "FileNotFoundError" in error_str or "Error while fetching server API version" in error_str:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Docker connection failed. Please ensure /var/run/docker.sock is mounted.",
                "original_error": error_str
            },
        )

    # Generic fallback for other Docker errors
    return JSONResponse(
        status_code=500,
        content={"detail": "Docker API Error", "original_error": error_str},
    )

@app.exception_handler(requests.exceptions.ConnectionError)
async def requests_connection_error_handler(request: Request, exc: requests.exceptions.ConnectionError):
    """
    Handle Requests connection errors that might leak from Docker SDK.
    """
    logger.error(f"Request Connection Error: {exc}")
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Connection error. This may indicate the Docker socket is not available.",
            "original_error": str(exc)
        },
    )

# Register Routers
app.include_router(users.router, prefix="/auth", tags=["users"])
app.include_router(smtp.router, prefix="/settings/smtp", tags=["smtp"])
app.include_router(auth_2fa.router, prefix="/auth/2fa", tags=["2fa"])
app.include_router(watchtower.router, prefix="/watchtower", tags=["watchtower"])
app.include_router(apps.router, prefix="/apps", tags=["apps"])
app.include_router(containers.router, prefix="/containers", tags=["containers"])
app.include_router(
    resources.router,
    prefix="/resources",
    tags=["resources"],
)
app.include_router(templates.router, prefix="/templates", tags=["templates"])
app.include_router(registries.router)
app.include_router(compose.router, prefix="/compose", tags=["compose"])
app.include_router(app_settings.router, prefix="/settings", tags=["settings"])
app.include_router(setup.router, prefix="/setup", tags=["setup"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(search.router, prefix="/search", tags=["search"])

if __name__ == "__main__":
    # FIX: Use 'api.main:app' to ensure correct module resolution when running via python -m
    # Or better, pass the app object directly if possible, but Uvicorn reloader needs import string.
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
