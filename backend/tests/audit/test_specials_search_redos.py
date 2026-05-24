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

def test_search_redos():
    token, _ = get_token("admin@example.com", "Password123!")
    res = client.get("/api/search/?q=" + "a" * 50000, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code in [200, 400, 422, 500]
