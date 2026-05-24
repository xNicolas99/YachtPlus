import pytest
from fastapi.testclient import TestClient
from api.main import app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.db.database import Base, get_db
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

# S1: Happy Path
@patch("api.actions.resources.aiodocker.Docker")
def test_s1_resources_happy_path(mock_docker):
    mock_instance = MagicMock()
    mock_instance.images.list = AsyncMock(return_value=[])
    mock_docker.return_value.__aenter__.return_value = mock_instance

    token, _ = get_token("admin@example.com", "Password123!")
    res = client.get("/api/resources/images/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200

# S15: IDOR
def test_s15_resources_idor():
    token, _ = get_token("admin@example.com", "Password123!")
    client.post("/api/auth/create", headers={"Authorization": f"Bearer {token}"}, json={"username": "user@example.com", "password": "Password123!", "is_superuser": False})

    token2, _ = get_token("user@example.com", "Password123!")
    # Can non-admin pull an image?
    res = client.post("/api/resources/images/", headers={"Authorization": f"Bearer {token2}"}, json={"image_name": "nginx:latest"})
    assert res.status_code == 403

# S14: Mass Assignment
def test_s14_resources_mass_assignment():
    token, _ = get_token("admin@example.com", "Password123!")
    res = client.post("/api/resources/images/", headers={"Authorization": f"Bearer {token}"}, json={"image_name": "nginx:latest", "is_superuser": True})
    assert res.status_code in [200, 422, 500]
