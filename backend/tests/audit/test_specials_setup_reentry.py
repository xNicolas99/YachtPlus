import pytest
from fastapi.testclient import TestClient
from api.main import app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.db.database import Base, get_db
from api.db.models import User
import pyotp
import jwt
from unittest.mock import patch

SQLALCHEMY_DATABASE_URL = "sqlite:///test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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

def test_setup_reentry():
    # Setup is already completed
    res = client.post("/api/setup/register", json={"username": "hacker@example.com", "password": "Password123!"})
    assert res.status_code in [403, 409, 400]
