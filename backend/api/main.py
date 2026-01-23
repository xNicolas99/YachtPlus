from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os

from api.routers import apps, dashboard, templates, resources, compose, settings as settings_router, users, auth_2fa, audit, registries
from api.db.database import engine, Base, SessionLocal
from api.db.models.users import User
from api.settings import get_settings

# Create DB Tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="YachtPlus API")

# Setup Status Logic
class SetupStatus:
    is_complete = False

setup_status = SetupStatus()

@app.on_event("startup")
def startup_event():
    # Check if user exists to skip setup
    db = SessionLocal()
    try:
        if db.query(User).first():
            setup_status.is_complete = True
            print("User found. Setup marked as COMPLETE.")
        else:
            print("No user found. Setup required.")
    except Exception as e:
        print(f"Database check failed: {e}")
    finally:
        db.close()

@app.middleware("http")
async def check_setup_status(request: Request, call_next):
    path = request.url.path
    if (path.startswith("/api/auth") or
        path.startswith("/assets") or
        path.startswith("/img") or
        "/favicon.ico" in path or
        request.method == "OPTIONS"):
        return await call_next(request)

    if not setup_status.is_complete:
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

app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(apps.router, prefix="/api/apps", tags=["apps"])
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
app.include_router(resources.router, prefix="/api/resources", tags=["resources"])
app.include_router(compose.router, prefix="/api/compose", tags=["compose"])
app.include_router(registries.router, prefix="/api/registries", tags=["registries"])
app.include_router(users.router, prefix="/api/auth", tags=["auth"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])

if os.path.exists("../frontend/dist"):
    app.mount("/", StaticFiles(directory="../frontend/dist", html=True), name="static")
