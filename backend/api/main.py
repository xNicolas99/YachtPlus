import uvicorn
from fastapi import Depends, FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from api.db.models.settings import TokenBlacklist
from api.settings import Settings
from api.utils.auth import get_db
from api.db.models.containers import TemplateVariables, Base
from api.db.models.settings import SecretKey
from api.db.database import SessionLocal, engine
from api.db.schemas.users import UserCreate
from api.db.crud.settings import generate_secret_key
from api.db.crud.users import create_user, get_users
from api.routers import apps, app_settings, compose, resources, templates, users, smtp, auth_2fa, watchtower, containers, dashboard, registries
from api.routers.setup import setup
from api.db.crud.templates import read_template_variables, set_template_variables
from api.services.watchtower import start_scheduler, stop_scheduler
import docker.errors
import requests.exceptions

app = FastAPI(root_path="/api")

settings = Settings()


@app.exception_handler(docker.errors.DockerException)
async def docker_exception_handler(request: Request, exc: docker.errors.DockerException):
    """
    Handle Docker exceptions gracefully, specifically targeting connection errors
    likely caused by missing socket mounts or permission issues.
    """
    error_str = str(exc)

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
app.include_router(
    templates.router,
    prefix="/templates",
    tags=["templates"],
)
app.include_router(registries.router)
app.include_router(compose.router, prefix="/compose", tags=["compose"])
app.include_router(app_settings.router, prefix="/settings", tags=["settings"])
app.include_router(setup.router, prefix="/setup", tags=["setup"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])


@app.on_event("startup")
async def startup(db: Session = Depends(get_db)):
    Base.metadata.create_all(bind=engine)
    start_scheduler()

    # Initialize Persistent Secret Key
    key = generate_secret_key(db=SessionLocal())
    from api.auth import jwt
    jwt.set_secret_key(key)

    users_exist = get_users(db=SessionLocal())
    print(
        "DISABLE_AUTH = "
        + str(settings.DISABLE_AUTH)
        + " ("
        + str(type(settings.DISABLE_AUTH))
        + ")"
    )
    if users_exist:
        print("Users Exist")
    template_variables_exist = read_template_variables(SessionLocal())
    if template_variables_exist:
        print("Template Variables Exist")
    else:
        print("No Variables yet!")
        t_vars = settings.BASE_TEMPLATE_VARIABLES
        t_var_list = []
        for t in t_vars:
            template_variables = TemplateVariables(
                variable=t.get("variable"), replacement=t.get("replacement")
            )
            t_var_list.append(template_variables)
        set_template_variables(new_variables=t_var_list, db=SessionLocal())

@app.on_event("shutdown")
def shutdown_event():
    stop_scheduler()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
