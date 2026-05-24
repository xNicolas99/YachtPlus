import pytest
import json
import os
from fastapi.testclient import TestClient
from api.main import app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.db.database import Base, get_db
import pyotp
from unittest.mock import patch

# --- Setup Test DB and Auth Context ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
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

client = TestClient(app, base_url="http://127.0.0.1")

def do_setup():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    res = client.post("/api/setup/register", json={"username": "admin@example.com", "password": "Password123!"})
    cookies = res.cookies
    res2 = client.get("/api/auth/2fa/generate", cookies=cookies)
    secret = res2.json()["secret"]
    totp = pyotp.TOTP(secret)
    client.post("/api/auth/2fa/enable", json={"code": totp.now()}, cookies=cookies)
    client.post("/api/setup/finalize", cookies=cookies)
    res5 = client.post("/api/auth/login", json={"username": "admin@example.com", "password": "Password123!", "otp_token": totp.now()})
    return res5.json().get("access_token"), dict(client.cookies)

# Get routes dynamically
all_routes = []
for r in app.routes:
    name = getattr(r, 'name', '')
    if not name:
        continue
    # we don't test static files or openapi directly via mechanical if it's too weird, but let's keep them
    methods = getattr(r, 'methods', ['GET'])
    # filter out HEAD and OPTIONS if GET exists
    if 'GET' in methods:
        primary_method = 'GET'
    elif 'POST' in methods:
        primary_method = 'POST'
    elif 'PUT' in methods:
        primary_method = 'PUT'
    elif 'PATCH' in methods:
        primary_method = 'PATCH'
    elif 'DELETE' in methods:
        primary_method = 'DELETE'
    else:
        primary_method = list(methods)[0]

    all_routes.append({
        "path": r.path,
        "method": primary_method,
        "all_methods": methods,
        "name": name,
        "dependencies": getattr(r, "dependencies", []),
        "body_field": getattr(r, "body_field", None),
    })

results = []

def record_result(endpoint, method, scenario, expected, actual, snippet):
    passed = actual == expected or (expected == "422_or_2xx" and actual in [200, 201, 202, 204, 422])
    if isinstance(expected, list):
         passed = actual in expected

    res = {
        "endpoint": endpoint,
        "method": method,
        "scenario": scenario,
        "expected_status": expected,
        "actual_status": actual,
        "pass": passed,
        "response_snippet": snippet[:200]
    }
    results.append(res)
    # Save incrementally
    os.makedirs("test_results", exist_ok=True)
    with open("test_results/matrix_mechanical.json", "w") as f:
        json.dump(results, f, indent=2)

@pytest.fixture(scope="module")
def auth_data():
    token, cookies = do_setup()
    client.cookies.clear()
    return {"token": token, "cookies": cookies}

@pytest.mark.parametrize("route", all_routes)
def test_s2_no_token(route):
    path = route["path"].replace("{", "dummy").replace("}", "") # dummy for path params

    if route["method"] == "GET":
        res = client.get(path)
    elif route["method"] == "POST":
        res = client.post(path, json={})
    elif route["method"] == "PUT":
        res = client.put(path, json={})
    elif route["method"] == "DELETE":
        res = client.delete(path)
    else:
        res = client.request(route["method"], path)

    expected = 401

    is_public = any(p in path for p in ["/docs", "/openapi.json", "/api/auth/login", "/api/setup/register", "/api/setup/status"])
    if is_public:
         expected = [200, 422, 400]

    record_result(path, route["method"], "S2", expected, res.status_code, res.text)

@pytest.mark.parametrize("route", all_routes)
def test_s3_invalid_token(route):
    path = route["path"].replace("{", "dummy").replace("}", "")
    is_public = any(p in path for p in ["/docs", "/openapi.json", "/api/auth/login", "/api/setup/register", "/api/setup/status"])

    headers = {"Authorization": "Bearer invalid.jwt.token"}
    if route["method"] == "GET":
        res = client.get(path, headers=headers)
    elif route["method"] == "POST":
        res = client.post(path, json={}, headers=headers)
    elif route["method"] == "PUT":
        res = client.put(path, json={}, headers=headers)
    elif route["method"] == "DELETE":
        res = client.delete(path, headers=headers)
    else:
        res = client.request(route["method"], path, headers=headers)

    expected = 401 if not is_public else [200, 422, 400]
    record_result(path, route["method"], "S3", expected, res.status_code, res.text)

@pytest.mark.parametrize("route", all_routes)
def test_s5_wrong_method(route, auth_data):
    path = route["path"].replace("{", "dummy").replace("}", "")
    all_methods = {"GET", "POST", "PUT", "PATCH", "DELETE"}
    allowed_methods = route["all_methods"]
    disallowed = list(all_methods - set(allowed_methods))
    if not disallowed:
        record_result(path, "ALL", "S5", "N/A", "N/A", "All methods allowed")
        return

    wrong_method = disallowed[0]
    headers = {"Authorization": f"Bearer {auth_data['token']}"}
    res = client.request(wrong_method, path, headers=headers)

    # We expect 405 Method Not Allowed
    record_result(path, wrong_method, "S5", 405, res.status_code, res.text)

@pytest.mark.parametrize("route", all_routes)
def test_s6_empty_body(route, auth_data):
    path = route["path"].replace("{", "dummy").replace("}", "")
    if route["method"] not in ["POST", "PUT", "PATCH"]:
        record_result(path, route["method"], "S6", "N/A", "N/A", "GET-only, no body accepted")
        return

    headers = {"Authorization": f"Bearer {auth_data['token']}", "Content-Type": "application/json"}
    res = client.request(route["method"], path, headers=headers, content="")

    record_result(path, route["method"], "S6", 422, res.status_code, res.text)

@pytest.mark.parametrize("route", all_routes)
def test_s20_wrong_content_type(route, auth_data):
    path = route["path"].replace("{", "dummy").replace("}", "")
    if route["method"] not in ["POST", "PUT", "PATCH"]:
        record_result(path, route["method"], "S20", "N/A", "N/A", "GET-only, no body accepted")
        return

    headers = {"Authorization": f"Bearer {auth_data['token']}", "Content-Type": "text/plain"}
    res = client.request(route["method"], path, headers=headers, content='{"valid": "json"}')

    record_result(path, route["method"], "S20", [415, 422], res.status_code, res.text)
