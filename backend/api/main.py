from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os

# Import ALL routers (Fixed 'settings' -> 'app_settings')
from api.routers import (
    apps, dashboard, templates, resources, compose,
    app_settings, users, auth_2fa, audit, registries,
    containers, smtp, watchtower, search, setup
)
from api.db.database import engine, Base, SessionLocal
from api.db.models.users import User
from api.settings import get_settings

Base.metadata.create_all(bind=engine)

app = FastAPI(title="YachtPlus API")

# --- ROBUST SETUP CHECK ---
from api.routers.setup.setup import is_setup_completed

@app.middleware("http")
async def check_setup_status(request: Request, call_next):
    path = request.url.path
    # Whitelist static assets and auth endpoints
    if (path.startswith("/api/auth") or path.startswith("/assets") or
        path.startswith("/img") or "/favicon.ico" in path or
        request.method == "OPTIONS"):
        return await call_next(request)

    # Check setup status using the router's logic (DB + File)
    # We use a fresh session for the check to ensure we get the latest DB state
    db = SessionLocal()
    try:
        setup_complete = is_setup_completed(db)
    finally:
        db.close()

    if not setup_complete:
        # Allow access to setup endpoints
        if not path.startswith("/api/setup"):
             if path.startswith("/api"):
                 return JSONResponse(status_code=428, content={"detail": "Setup required"})

    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # CSP: Allow self, unsafe-inline, NO unsafe-eval
    response.headers["Content-Security-Policy"] = "script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self';"
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
