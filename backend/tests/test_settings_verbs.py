"""B-11: mutating settings endpoints must use POST, not GET."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import app_settings
from api.auth.jwt import get_auth_wrapper


class _DummyAuth:
    def __init__(self, request):
        pass

    async def jwt_required(self, allow_setup_pending=False):
        return None

    async def get_jwt_subject(self, allow_setup_pending=False):
        return "admin"


class _DummyAuthorize:
    def __init__(self, request):
        self.user = None

    async def jwt_required(self, allow_setup_pending=False):
        return None

    async def get_jwt_subject(self, allow_setup_pending=False):
        return "admin"


def _override_auth():
    return _DummyAuth(None)


def test_prune_and_update_are_post_only():
    app = FastAPI()
    app.include_router(app_settings.router, prefix="/settings")
    app.dependency_overrides[get_auth_wrapper] = _override_auth
    client = TestClient(app)

    # GET must be disallowed or at least not be the primary route
    for path in ["/settings/prune/images", "/settings/update"]:
        r = client.get(path)
        # Either 405 or 403/401 because of auth/superuser; not 200
        assert r.status_code in (405, 403, 401), f"GET {path} returned {r.status_code}"
