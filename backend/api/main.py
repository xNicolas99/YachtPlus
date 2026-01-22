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
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Use the new error handler
from api.utils.error_handler import sanitize_error_message
from api.db.models.settings import TokenBlacklist
from api.settings import Settings
from api.utils.auth import get_db
from api.db.models.containers import TemplateVariables, Base
from api.db.models.settings import SecretKey
from api.db.database import SessionLocal, engine
from api.db.schemas.users import UserCreate
from api.db.crud.settings import generate_secret_key
from api.db.crud.users import create_user, get_users
from api.routers import apps, app_settings, compose, resources, templates, users, smtp, auth_2fa, watchtower, containers, dashboard, registries, search, audit
from api.routers import setup
from api.db.crud.templates import read_template_variables, set_template_variables, get_templates, add_template
from api.db.models.containers import Template
from api.db.models.setup import SetupStatus
from api.services.watchtower import start_scheduler, stop_scheduler
import os
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
    scheduler_lock_file = "/tmp/yachtplus_scheduler.lock"
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
            # Auto-Discovery: If users exist, ensure setup is marked as complete.
            # This handles cases where the volume is persistent but the flag file is missing.
            try:
                setup_status = db.query(SetupStatus).first()
                if not setup_status:
                    setup_status = SetupStatus(is_complete=True)
                    db.add(setup_status)
                    db.commit()
                    logger.info("Auto-Discovery: Created SetupStatus entry for existing users.")
                elif not setup_status.is_complete:
                    setup_status.is_complete = True
                    db.commit()
                    logger.info("Auto-Discovery: Updated SetupStatus to complete for existing users.")

                # Ensure legacy marker file exists
                if not os.path.exists("/config/.setup_completed"):
                    try:
                        os.makedirs("/config", exist_ok=True)
                        with open("/config/.setup_completed", "w") as f:
                            f.write("Setup completed")
                        logger.info("Auto-Discovery: Created .setup_completed marker file.")
                    except OSError as e:
                        logger.warning(f"Auto-Discovery: Failed to create marker file: {e}")
            except Exception as e:
                logger.error(f"Auto-Discovery Error: {e}")

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

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Overrides the default validation error handler to sanitize sensitive data.
    Logs the full error server-side, but returns a generic or sanitized message to the client.
    """
    logger.warning(f"Validation Error: {exc.errors()} - Body: {exc.body}")

    # Check if this is an auth endpoint where we want to be extra generic
    path = request.url.path
    if "/auth/login" in path or "/auth/register" in path or "/setup" in path:
         return JSONResponse(
            status_code=422,
            content={"detail": "Validation error: required field(s) missing or invalid. Please check your input."}
        )

    # For other endpoints, we can be more specific but still sanitized
    sanitized_errors = sanitize_error_message(exc.errors())

    return JSONResponse(
        status_code=422,
        content={"detail": sanitized_errors}
    )

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

    # Use a separate session for middleware to check DB state
    db = SessionLocal()
    setup_done = False
    try:
        # Primary: Check DB
        setup_status = db.query(SetupStatus).first()
        if setup_status:
            setup_done = setup_status.is_complete

        # Fallback: Check file (for old deployments or migration safety)
        if not setup_done and os.path.exists("/config/.setup_completed"):
            setup_done = True
            # Write to DB for future if not present
            if not setup_status:
                new_status = SetupStatus(is_complete=True)
                db.add(new_status)
                db.commit()
            elif not setup_status.is_complete:
                 setup_status.is_complete = True
                 db.commit()
    except Exception as e:
        logger.error(f"Setup check failed: {e}")
        # Fail safe? Or Fail secure?
        # If DB is down, we probably can't do much anyway.
        pass
    finally:
        db.close()

    if not setup_done:
        path = request.url.path

        # Normalize path: If it starts with /api/, strip it to match our router definitions
        if path.startswith("/api/"):
            path = path[4:] # Remove /api prefix

        allowed_prefixes = [
            "/setup",
            "/auth/login",
            "/auth/register",
            "/auth/me",
            "/auth/jwt/login",
            "/auth/2fa",
            "/auth/logout",
            "/auth/users",
            "/settings",
            "/manifest.json",
            "/docs", "/openapi.json", "/redoc"
        ]

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
app.include_router(audit.router, prefix="/audit", tags=["audit"])

if __name__ == "__main__":
    # FIX: Use 'api.main:app' to ensure correct module resolution when running via python -m
    # Or better, pass the app object directly if possible, but Uvicorn reloader needs import string.
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
