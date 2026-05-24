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

# S1: Happy Path
@patch("api.actions.compose.os.listdir")
@patch("api.actions.compose.os.path.isdir")
def test_s1_compose_happy_path(mock_isdir, mock_listdir):
    mock_isdir.return_value = True
    mock_listdir.return_value = ["project1", "project2"]
    token, _ = get_token("admin@example.com", "Password123!")
    res = client.get("/api/compose/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert "project1" in str(res.content)

# S10: Command Injection in Compose Action
@patch("api.actions.compose.subprocess.run")
def test_s10_compose_command_injection(mock_subprocess_run):
    token, _ = get_token("admin@example.com", "Password123!")
    res = client.post("/api/compose/--version/up", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code in [400, 422, 500, 404]

# S15: IDOR
def test_s15_compose_idor():
    token, _ = get_token("admin@example.com", "Password123!")
    client.post("/api/auth/create", headers={"Authorization": f"Bearer {token}"}, json={"username": "user@example.com", "password": "Password123!", "is_superuser": False})
    token2, _ = get_token("user@example.com", "Password123!")
    res = client.get("/api/compose/", headers={"Authorization": f"Bearer {token2}"})
    assert res.status_code == 403

# S12: Path Traversal in Project Name
def test_s12_compose_path_traversal():
    token, _ = get_token("admin@example.com", "Password123!")
    res = client.get("/api/compose/..%2F..%2Fetc", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code in [400, 404, 500]
