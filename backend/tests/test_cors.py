from fastapi.testclient import TestClient
from api.main import app
import pytest

client = TestClient(app)

def test_cors_permissive():
    # Test that an arbitrary origin is NOT allowed
    origin = "http://evil.com"
    response = client.get("/api/auth/login", headers={"Origin": origin})

    # After the fix, the origin should NOT be reflected if it's not in the allowed list
    assert response.headers.get("access-control-allow-origin") != origin

def test_cors_allowed_origin():
    # Test that an allowed origin is allowed
    origin = "http://localhost"
    response = client.get("/api/auth/login", headers={"Origin": origin})

    assert response.headers.get("access-control-allow-origin") == origin
    assert response.headers.get("access-control-allow-credentials") == "true"

def test_cors_preflight_denied():
    origin = "http://evil.com"
    headers = {
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    }
    response = client.options("/api/auth/login", headers=headers)

    assert response.headers.get("access-control-allow-origin") != origin

def test_cors_preflight_allowed():
    origin = "http://localhost"
    headers = {
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    }
    response = client.options("/api/auth/login", headers=headers)

    assert response.headers.get("access-control-allow-origin") == origin
    assert response.headers.get("access-control-allow-credentials") == "true"
