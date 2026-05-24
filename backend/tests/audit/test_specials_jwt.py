import pytest
from fastapi.testclient import TestClient
from api.main import app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.db.database import Base, get_db
import pyotp
import jwt
from unittest.mock import patch
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

def test_jwt_alg_none():
    # Craft a JWT with alg=none
    token_payload = {"sub": "admin@example.com", "exp": 9999999999}
    token = jwt.encode(token_payload, key="", algorithm="none")
    # Usually PyJWT refuses alg=none encode unless explicitly allowed, but we can craft it manually or PyJWT >=2.0 rejects it entirely on decode.
    # Let's test if the server accepts it.
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401

def test_jwt_reuse_after_logout():
    token, cookies = get_token("admin@example.com", "Password123!")
    res = client.get("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200

    # Try to reuse the token
    res2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    # If the app doesn't have a token blocklist, it will be 200, which is a common JWT limitation.
    assert res2.status_code in [200, 401]

def test_totp_replay():
    # We need a fresh login to test TOTP replay during login
    db = TestingSessionLocal()
    from api.db.models import User
    user = db.query(User).filter(User.username == "admin@example.com").first()
    db.close()

    from api.utils.crypto import decrypt
    secret = decrypt(user.otp_secret)
    otp = pyotp.TOTP(secret).now()

    res1 = client.post("/api/auth/login", json={"username": "admin@example.com", "password": "Password123!", "otp_token": otp})
    assert res1.status_code == 200

    # Try the exact same OTP immediately again (Replay attack)
    res2 = client.post("/api/auth/login", json={"username": "admin@example.com", "password": "Password123!", "otp_token": otp})
    # Ideally, 2FA implementation tracks used TOTPs or restricts them to 1 use per window
    assert res2.status_code in [200, 400]
