import logging
import uvicorn
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
from api.routers import apps, app_settings, compose, resources, templates, users, smtp, auth_2fa, watchtower, containers, dashboard, registries, search, dashboard_sse
from api.routers.setup import setup
from api.db.crud.templates import read_template_variables, set_template_variables, get_templates, add_template
from api.db.models.containers import Template
from api.services.watchtower import start_scheduler, stop_scheduler
import docker.errors
import requests.exceptions

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = Settings()

# Setup Rate Limiter
limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up...")
    Base.metadata.create_all(bind=engine)
    start_scheduler()

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
    stop_scheduler()

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

    # CSP: Mitigate XSS risks (especially important for Vue 2 EOL).
    # We allow 'unsafe-inline' for styles because Vuetify 2 uses them heavily.
    # We allow 'unsafe-eval' for Vue 2 runtime compiler if used (often needed).
    # Ideally, this should be stricter, but 'self' is a good start.
    # NOTE: 'unsafe-eval' is REQUIRED for Vue 2 runtime template compilation.
    # Removing it will break the application. Migration to Vue 3 + Vite is the only permanent fix.
    csp_policy = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-eval' 'unsafe-inline'; "
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
app.include_router(dashboard_sse.router, prefix="/dashboard", tags=["dashboard-sse"])
app.include_router(search.router, prefix="/search", tags=["search"])

if __name__ == "__main__":
    # FIX: Use 'api.main:app' to ensure correct module resolution when running via python -m
    # Or better, pass the app object directly if possible, but Uvicorn reloader needs import string.
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
