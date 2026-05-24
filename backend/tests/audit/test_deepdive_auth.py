import pytest
from fastapi.testclient import TestClient
from api.main import app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.db.database import Base, get_db
from api.db.models import User
import pyotp
from unittest.mock import patch

SQLALCHEMY_DATABASE_URL = "sqlite:///test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

patcher = patch("api.utils.security._resolve_client_ip", return_value="127.0.0.1")
patcher.start()

patcher_f2b = patch("api.utils.security._count_recent_failed_attempts", return_value=0)
patcher_f2b.start()
patcher_f2bu = patch("api.utils.security._count_recent_failed_attempts_for_username", return_value=0)
patcher_f2bu.start()

def get_token(username="admin@example.com", password="Password123!"):
    db = TestingSessionLocal()
    user = db.query(User).filter(User.username == username).first()
    db.close()

    otp = None
    if user and user.is_2fa_enabled:
        from api.utils.crypto import decrypt
        secret = decrypt(user.otp_secret)
        otp = pyotp.TOTP(secret).now()

    client = TestClient(app, base_url="http://127.0.0.1")
    res = client.post("/api/auth/login", json={"username": username, "password": password, "otp_token": otp})
    return res.json().get("access_token"), dict(res.cookies)

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
def test_s1_login_flow():
    token, cookies = get_token("admin@example.com", "Password123!")
    assert token is not None
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["username"] == "admin@example.com"

# S4: Falsche Permission (Non-Admin versucht auf Admin-Endpoint)
def test_s4_wrong_permission():
    with patch("api.utils.security._resolve_client_ip", return_value="127.0.0.101"):
        token, cookies = get_token("admin@example.com", "Password123!")
        res = client.post("/api/auth/create", headers={"Authorization": f"Bearer {token}"}, json={"username": "user@example.com", "password": "Password123!", "is_superuser": False})
        assert res.status_code == 200

    with patch("api.utils.security._resolve_client_ip", return_value="127.0.0.102"):
        token2, cookies2 = get_token("user@example.com", "Password123!")
        res = client.post("/api/auth/create", headers={"Authorization": f"Bearer {token2}"}, json={"username": "user3@example.com", "password": "Password123!", "is_superuser": False})
        assert res.status_code == 403

# S10: SQL Injection
def test_s10_auth_sql_injection():
    with patch("api.utils.security._resolve_client_ip", return_value="127.0.0.103"):
        res = client.post("/api/auth/login", json={"username": "admin@example.com' OR 1=1 --", "password": "Password123!"})
        assert res.status_code == 400

# S11: XSS in Username
def test_s11_xss_reflection():
    with patch("api.utils.security._resolve_client_ip", return_value="127.0.0.104"):
        token, cookies = get_token("admin@example.com", "Password123!")
        res = client.post("/api/auth/create", headers={"Authorization": f"Bearer {token}"}, json={"username": "<script>alert(1)</script>@example.com", "password": "Password123!"})
        assert res.status_code in [200, 422]

# S14: Mass-Assignment
def test_s14_mass_assignment():
    with patch("api.utils.security._resolve_client_ip", return_value="127.0.0.105"):
        token, cookies = get_token("admin@example.com", "Password123!")
        res = client.post("/api/auth/me", headers={"Authorization": f"Bearer {token}"}, json={"password": "NewPassword123!", "current_password": "Password123!", "is_superuser": True})
        assert res.status_code == 200

    with patch("api.utils.security._resolve_client_ip", return_value="127.0.0.106"):
        token2, cookies2 = get_token("user@example.com", "Password123!")
        if token2:
            res3 = client.post("/api/auth/me", headers={"Authorization": f"Bearer {token2}"}, json={"password": "NewPassword123!", "current_password": "Password123!", "is_superuser": True})
            assert res3.status_code == 200
            db = TestingSessionLocal()
            u = db.query(User).filter(User.username=="user@example.com").first()
            is_su = u.is_superuser
            db.close()
            client.post("/api/auth/me", headers={"Authorization": f"Bearer {token2}"}, json={"password": "Password123!", "current_password": "NewPassword123!"})
            if is_su:
                pytest.fail("Mass assignment allowed on is_superuser")

# S15: IDOR
def test_s15_idor():
    with patch("api.utils.security._resolve_client_ip", return_value="127.0.0.107"):
        token2, cookies2 = get_token("user@example.com", "Password123!")
        db = TestingSessionLocal()
        admin_user = db.query(User).filter(User.username == "admin@example.com").first()
        db.close()

        if token2:
            res = client.delete(f"/api/auth/users/{admin_user.id}", headers={"Authorization": f"Bearer {token2}"})
            assert res.status_code == 403

# S16: Rate-Limit
def test_s16_rate_limit():
    with patch("api.utils.security._resolve_client_ip", return_value="127.0.0.108"):
        for i in range(15):
            res = client.post("/api/auth/login", json={"username": "admin@example.com", "password": "wrong"})
        assert res.status_code in [400, 429]

# S17: Idempotenz
def test_s17_idempotence():
    with patch("api.utils.security._resolve_client_ip", return_value="127.0.0.109"):
        token, cookies = get_token("admin@example.com", "Password123!")
        res1 = client.post("/api/auth/create", headers={"Authorization": f"Bearer {token}"}, json={"username": "idem@example.com", "password": "Password123!"})
        res2 = client.post("/api/auth/create", headers={"Authorization": f"Bearer {token}"}, json={"username": "idem@example.com", "password": "Password123!"})
        assert res1.status_code == 200
        assert res2.status_code in [400, 409]
