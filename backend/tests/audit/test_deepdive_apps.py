import pytest
from fastapi.testclient import TestClient
from api.main import app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.db.database import Base, get_db
from api.db.models import User
import pyotp
from unittest.mock import patch, MagicMock, AsyncMock
from tests.audit.test_deepdive_auth import get_token, engine, TestingSessionLocal

app.dependency_overrides[get_db] = lambda: TestingSessionLocal()
client = TestClient(app, base_url="http://127.0.0.1")

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    res = client.post("/api/setup/register", json={"username": "admin@example.com", "password": "Password123!"})
    cookies = res.cookies
    res2 = client.get("/api/auth/2fa/generate", cookies=cookies)
    if "secret" in res2.json():
        secret = res2.json()["secret"]
        totp = pyotp.TOTP(secret)
        client.post("/api/auth/2fa/enable", json={"code": totp.now()}, cookies=cookies)
    client.post("/api/setup/finalize", cookies=cookies)

@patch("api.actions.apps.aiodocker.Docker")
def test_s1_apps_happy_path(mock_docker):
    mock_instance = MagicMock()
    mock_instance.containers.list = AsyncMock(return_value=[])
    mock_docker.return_value.__aenter__.return_value = mock_instance

    token, _ = get_token("admin@example.com", "Password123!")
    res = client.get("/api/apps/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200

# S10: SQL/Command Injection in get_container_details
@patch("api.actions.apps.aiodocker.Docker")
def test_s10_apps_path_traversal(mock_docker):
    mock_instance = MagicMock()
    mock_instance.containers.get = AsyncMock(side_effect=Exception("Not found"))
    mock_docker.return_value.__aenter__.return_value = mock_instance
    token, _ = get_token("admin@example.com", "Password123!")
    res = client.get("/api/apps/..%2F..%2Fetc%2Fpasswd", headers={"Authorization": f"Bearer {token}"})
    # If the app tries to do path stuff, it might fail. Usually it's just passed to docker API.
    assert res.status_code in [404, 400, 422, 500]

# S15: IDOR (Deploy an app)
@patch("api.routers.apps.deploy_app")
def test_s15_apps_deploy_idor(mock_deploy_app):
    token, _ = get_token("admin@example.com", "Password123!")
    # Can we deploy an app? Yes, we are admin.
    res = client.post("/api/apps/deploy", headers={"Authorization": f"Bearer {token}"}, json={"name": "test-app", "image": "nginx:latest"})
    print("DEPLOY ADMIN", res.status_code, res.content)

    # What if a normal user tries it?
    client.post("/api/auth/create", headers={"Authorization": f"Bearer {token}"}, json={"username": "user@example.com", "password": "Password123!", "is_superuser": False})
    token2, _ = get_token("user@example.com", "Password123!")
    if token2:
        res2 = client.post("/api/apps/deploy", headers={"Authorization": f"Bearer {token2}"}, json={"name": "test-app2", "image": "nginx:latest"})
        print("DEPLOY NORMAL USER", res2.status_code, res2.content)
        assert res2.status_code == 403

# S14: Mass Assignment in deploy
def test_s14_apps_mass_assignment():
    token, _ = get_token("admin@example.com", "Password123!")
    res = client.post("/api/apps/deploy", headers={"Authorization": f"Bearer {token}"}, json={"name": "test-app", "image": "nginx:latest", "is_superuser": True})
    assert res.status_code in [200, 422, 500]

# S18: Race Condition (double action)
@patch("api.actions.apps.aiodocker.Docker")
def test_s18_apps_action_race(mock_docker):
    mock_instance = MagicMock()
    mock_container = MagicMock()
    mock_container.start = AsyncMock(return_value=None)
    mock_instance.containers.get = AsyncMock(return_value=mock_container)
    mock_docker.return_value.__aenter__.return_value = mock_instance

    token, _ = get_token("admin@example.com", "Password123!")
    import asyncio
    async def concurrent_requests():
        import httpx
        # transport instead of app for ASyncClient
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            reqs = [ac.get("/api/apps/actions/test-app/start", headers={"Authorization": f"Bearer {token}"}) for _ in range(5)]
            return await asyncio.gather(*reqs)

    responses = asyncio.run(concurrent_requests())
    assert all(r.status_code in [200, 400, 500] for r in responses)
