"""Regression for BUG-001 + the private-network access requirement.

The previous default ALLOWED_HOSTS was ["localhost", "127.0.0.1", "[::1]"],
which meant every request arriving via a LAN IP (e.g. http://192.168.1.42:8000/)
was rejected with `400 Invalid host header` before any router could run.

The replacement middleware:
  - keeps the strict whitelist when YACHT_ALLOWED_HOSTS is set,
  - honours "*" as a "disable host pinning" escape hatch,
  - and (by default, controlled by ALLOW_PRIVATE_NETWORK_HOSTS) accepts
    any RFC 1918 / link-local / loopback IP literal in the Host header.
"""
import importlib
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(env, monkeypatch):
    """Reload api.settings + api.main with the given env so the
    middleware picks up our test values from module-level resolution.
    """
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv(
        "YACHT_CORS_ORIGINS",
        env.get("YACHT_CORS_ORIGINS", "http://localhost"),
    )
    import api.settings as settings_module
    import api.main as main_module
    importlib.reload(settings_module)
    importlib.reload(main_module)
    # Strip the routers we don't need to keep collection fast — the
    # middleware is what we're testing.
    return main_module.app


def _client(app):
    return TestClient(app, raise_server_exceptions=False)


def test_private_ip_host_accepted_by_default(monkeypatch):
    app = _build_app({}, monkeypatch)
    client = _client(app)
    # 192.168.x.y is RFC 1918 — should be allowed by the default config.
    r = client.get("/api/setup/status", headers={"host": "192.168.1.42:8000"})
    assert r.status_code != 400, r.text


def test_link_local_ip_accepted_by_default(monkeypatch):
    app = _build_app({}, monkeypatch)
    client = _client(app)
    r = client.get("/api/setup/status", headers={"host": "169.254.1.5:8000"})
    assert r.status_code != 400, r.text


def test_public_ip_host_rejected_by_default(monkeypatch):
    app = _build_app({}, monkeypatch)
    client = _client(app)
    # 8.8.8.8 is not on the whitelist and not private -> still rejected.
    r = client.get("/api/setup/status", headers={"host": "8.8.8.8"})
    assert r.status_code == 400


def test_wildcard_accepts_anything(monkeypatch):
    app = _build_app({"YACHT_ALLOWED_HOSTS": "*"}, monkeypatch)
    client = _client(app)
    r = client.get("/api/setup/status", headers={"host": "evil.example.com"})
    assert r.status_code != 400, r.text


def test_strict_mode_rejects_private_ip(monkeypatch):
    """When ALLOW_PRIVATE_NETWORK_HOSTS=false the strict whitelist rules
    again (intended for public-internet deploys behind a real domain).
    """
    app = _build_app({
        "YACHT_ALLOWED_HOSTS": "yachtplus.example.com",
        "YACHT_ALLOW_PRIVATE_NETWORK_HOSTS": "false",
    }, monkeypatch)
    client = _client(app)
    r = client.get("/api/setup/status", headers={"host": "192.168.1.42:8000"})
    assert r.status_code == 400


def test_strict_mode_accepts_configured_hostname(monkeypatch):
    app = _build_app({
        "YACHT_ALLOWED_HOSTS": "yachtplus.example.com",
        "YACHT_ALLOW_PRIVATE_NETWORK_HOSTS": "false",
    }, monkeypatch)
    client = _client(app)
    r = client.get("/api/setup/status", headers={"host": "yachtplus.example.com"})
    assert r.status_code != 400, r.text
