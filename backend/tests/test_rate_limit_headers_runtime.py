"""Exercise real slowapi decorators outside conftest's handler-call shim."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_real_limiter_handles_cookie_login_orm_dict_and_rate_limit_responses(tmp_path):
    environment = os.environ.copy()
    environment.update({
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'runtime.db').as_posix()}",
        "SECRET_KEY_FILE": str(tmp_path / "signing-key"),
        "FERNET_SALT_FILE": str(tmp_path / "fernet-salt"),
        "YACHT_ACCESS_POLICY_FILE": str(tmp_path / "access-policy.json"),
        "YACHT_FAIL2BAN_STATE_DIR": str(tmp_path / "security-state"),
        "YACHT_SECURITY_LOG": str(tmp_path / "auth.log"),
        "YACHT_FAIL2BAN_REQUIRED": "false",
        "YACHT_ALLOWED_HOSTS": "localhost,127.0.0.1",
        "RATE_LIMIT_STORAGE_URI": "memory://",
        "DISABLE_AUTH": "false",
        "SECURE_COOKIES": "false",
        "COMPOSE_AUTO_UPDATE": "false",
    })
    program = textwrap.dedent("""
        import asyncio
        import importlib
        from unittest.mock import AsyncMock

        from fastapi.testclient import TestClient
        from api.main import app
        from api.actions import resources
        from api.db.database import Base, SessionLocal, engine
        from api.db.crud.users import get_password_hash
        from api.db.models.setup import SetupStatus
        from api.db.models.users import User
        from api.utils.security import limiter

        assert limiter.enabled and limiter._headers_enabled
        # FastAPI must inject a Response for every decorated endpoint,
        # including routes whose normal result is serialized from an ORM row.
        checked = 0
        for name in limiter._route_limits:
            module_name, endpoint_name = name.rsplit(".", 1)
            module = importlib.import_module(module_name)
            route = next(route for route in module.router.routes
                         if getattr(route, "endpoint", None).__name__ == endpoint_name)
            assert route.dependant.response_param_name == "response", name
            checked += 1
        assert checked >= 40, checked

        async def seed():
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with SessionLocal() as session:
                session.add(User(username="runtime-user", hashed_password=await get_password_hash("runtime-password"),
                                 is_active=True, is_superuser=True))
                session.add(SetupStatus(is_complete=True))
                await session.commit()
        asyncio.run(seed())

        resources.get_images = AsyncMock(return_value={"items": [], "total": 0})
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            login = client.post("/api/auth/login_cookie", json={"username": "runtime-user", "password": "runtime-password"},
                                headers={"Origin": "http://localhost"})
            assert login.status_code == 200, login.text
            assert login.json()["login"] == "successful"
            assert login.headers["X-RateLimit-Limit"] == "5"
            assert "access_token_cookie" in client.cookies

            images = client.get("/api/resources/images/")
            assert images.status_code == 200, images.text
            assert images.json() == {"items": [], "total": 0}
            assert images.headers["X-RateLimit-Limit"] == "60"

            for attempt in range(20):
                profile = client.get("/api/auth/me")
                assert profile.status_code == 200, (attempt, profile.text)
                assert profile.json()["username"] == "runtime-user"
                assert profile.headers["X-RateLimit-Limit"] == "20"
                assert int(profile.headers["X-RateLimit-Remaining"]) == 19 - attempt
            blocked = client.get("/api/auth/me")
            assert blocked.status_code == 429, blocked.text
            assert blocked.headers["X-RateLimit-Limit"] == "20"
            assert int(blocked.headers["Retry-After"]) >= 0
            assert "Rate limit exceeded" in blocked.text
        print("real limiter: cookie login, dict, ORM, headers, 429 passed")
    """)
    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "real limiter: cookie login, dict, ORM, headers, 429 passed" in result.stdout
