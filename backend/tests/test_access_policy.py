"""Network isolation, forwarded IP attribution and fail-closed ban state."""
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.utils import access_policy as policy
from api.utils import security
from api.routers import app_settings


@pytest.fixture
def configuration(tmp_path, monkeypatch):
    settings = SimpleNamespace(
        ACCESS_POLICY_FILE=str(tmp_path / "access-policy.json"),
        FAIL2BAN_REQUIRED=False,
        FAIL2BAN_STATE_DIR=str(tmp_path / "state"),
        SECURITY_LOG=str(tmp_path / "logs" / "auth.log"),
        TRUSTED_PROXIES=["127.0.0.1", "::1"],
    )
    monkeypatch.setattr(policy, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "_settings", settings)
    monkeypatch.setattr(app_settings, "settings", settings)
    return settings


def ready(settings, timestamp=None, status="ready"):
    from pathlib import Path
    directory = Path(settings.FAIL2BAN_STATE_DIR)
    (directory / "bans").mkdir(parents=True, exist_ok=True)
    (directory / "ready.json").write_text(json.dumps({"timestamp": time.time() if timestamp is None else timestamp, "status": status}))
    return directory


def request(client_ip, headers=None):
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()], "client": (client_ip, 1234), "server": ("localhost", 80), "scheme": "http", "query_string": b""})


@pytest.fixture
def gated_app(configuration):
    async def endpoint(request):
        return JSONResponse({"reachable": True})

    async def socket(websocket):
        await websocket.accept()
        await websocket.send_text("reachable")
        await websocket.close()

    async def echo(websocket):
        await websocket.accept()
        try:
            while True:
                await websocket.send_text(await websocket.receive_text())
        except WebSocketDisconnect:
            pass

    app = Starlette(routes=[Route("/{path:path}", endpoint, methods=["GET", "POST", "OPTIONS"]), WebSocketRoute("/socket", socket), WebSocketRoute("/echo", echo)])
    app.add_middleware(policy.AccessPolicyMiddleware)
    return app


@pytest.mark.parametrize("address", ["127.0.0.1", "127.5.1.2", "10.0.0.1", "172.16.0.1", "172.31.255.255", "192.168.1.2", "::1", "fd12::1", "fc01::5", "::ffff:192.168.1.2"])
def test_explicit_local_ranges(address):
    assert policy.is_local_client(address)


@pytest.mark.parametrize("address", [None, "unknown", "localhost", "", "0.0.0.0", "::", "169.254.1.2", "fe80::1", "224.0.0.1", "ff02::1", "240.0.0.1", "100.64.0.1", "198.51.100.1", "8.8.8.8", "172.32.0.1", "fd12::1%eth0", "::ffff:8.8.8.8"])
def test_nonlocal_never_matches_lan(address):
    assert not policy.is_local_client(address)


@pytest.mark.parametrize("path", ["/", "/api/setup/register", "/api/auth/login_cookie", "/api/apps", "/assets/index.js"])
def test_public_blocked_before_all_routes(gated_app, path):
    response = TestClient(gated_app, client=("8.8.8.8", 1234)).get(path)
    assert response.status_code == 403


def test_actual_application_blocks_public_setup_before_validation(configuration):
    from api.main import app
    response = TestClient(app, client=("8.8.8.8", 1234)).post("/api/setup/register", json={})
    assert response.status_code == 403
    assert response.json()["detail"] == "Access restricted to local networks"


def test_actual_application_access_gate_is_outermost(configuration):
    from api.main import app
    response = TestClient(app).get("/api/apps", headers={"X-Real-IP": "8.8.8.8", "Host": "attacker.example"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Access restricted to local networks"


def test_actual_application_public_terminal_handshake_blocked(configuration):
    from api.main import app
    with pytest.raises(WebSocketDisconnect) as error:
        with TestClient(app, client=("8.8.8.8", 1234)).websocket_connect("/api/containers/example/exec"):
            pass
    assert error.value.code == 1008


def test_local_routes_reachable(gated_app):
    assert TestClient(gated_app, client=("192.168.1.5", 1234)).get("/api/setup/register").status_code == 200


def test_explicit_persisted_public_optin(configuration, gated_app):
    configuration.FAIL2BAN_REQUIRED = True
    ready(configuration)
    policy.write_access_policy(True, configuration)
    assert TestClient(gated_app, client=("8.8.8.8", 1234)).get("/").status_code == 200
    policy.write_access_policy(False, configuration)
    assert TestClient(gated_app, client=("8.8.8.8", 1234)).get("/").status_code == 403


@pytest.mark.parametrize("peer", ["testclient", "0.0.0.0", "::", "224.0.0.1", "198.51.100.2"])
def test_bad_sources_blocked_even_after_public_optin(configuration, gated_app, peer):
    policy.write_access_policy(True, configuration)
    assert TestClient(gated_app, client=(peer, 1234)).get("/").status_code == 403


def test_unknown_peer_headers_do_not_grant_loopback(gated_app):
    assert TestClient(gated_app, client=("testclient", 1234)).get("/", headers={"X-Real-IP": "127.0.0.1"}).status_code == 403


def test_trusted_nginx_forwarded_public_ip_blocked(gated_app):
    assert TestClient(gated_app).get("/", headers={"X-Real-IP": "8.8.8.8"}).status_code == 403


def test_untrusted_public_peer_cannot_spoof_local(gated_app):
    assert TestClient(gated_app, client=("8.8.8.8", 1234)).get("/", headers={"X-Real-IP": "127.0.0.1", "X-Forwarded-For": "192.168.1.1"}).status_code == 403


@pytest.mark.parametrize("header", ["localhost", "127.0.0.1, 8.8.8.8", "127.0.0.1\n", "bad", "fe80::1%eth0"])
def test_bad_real_ip_fails_closed(gated_app, header):
    # Leading/trailing whitespace is safely normalized; embedded separators
    # and scoped/nonusable addresses are rejected.
    if header == "127.0.0.1\n":
        header = "127.0.0.1\n8.8.8.8"
    assert TestClient(gated_app).get("/", headers={"X-Real-IP": header}).status_code == 403


def test_xff_stops_at_untrusted_private_boundary(configuration):
    assert security._resolve_client_ip(request("127.0.0.1", {"X-Forwarded-For": "8.8.8.8, 10.0.0.50"})) == "10.0.0.50"
    configuration.TRUSTED_PROXIES.append("10.0.0.50")
    assert security._resolve_client_ip(request("127.0.0.1", {"X-Forwarded-For": "8.8.8.8, 10.0.0.50"})) == "8.8.8.8"


def test_ipv4_mapped_addresses_share_rate_and_ban_identity(configuration):
    assert security._resolve_client_ip(request("::ffff:192.168.1.3")) == "192.168.1.3"
    assert policy.ban_filename("::ffff:192.168.1.3") == policy.ban_filename("192.168.1.3")
    assert policy.ban_filename("fd01::1") == "fd01__1.json"


def test_internal_auth_subrequest_returns204_before_routes(gated_app):
    assert TestClient(gated_app).get("/internal/access", headers={"X-Real-IP": "192.168.1.4"}).status_code == 204
    assert TestClient(gated_app).get("/internal/access", headers={"X-Real-IP": "8.8.8.8"}).status_code == 403


def test_internal_check_cannot_be_called_directly(gated_app):
    assert TestClient(gated_app).get("/internal/access").status_code == 403
    assert TestClient(gated_app, client=("192.168.1.4", 1234)).get("/internal/access", headers={"X-Real-IP": "192.168.1.4"}).status_code == 403
    assert TestClient(gated_app).post("/internal/access", headers={"X-Real-IP": "192.168.1.4"}).status_code == 403


def test_internal_check_requires_trusted_loopback(configuration, gated_app):
    configuration.TRUSTED_PROXIES = []
    assert TestClient(gated_app).get("/internal/access", headers={"X-Real-IP": "192.168.1.4"}).status_code == 403


@pytest.mark.parametrize("timestamp,status", [(0, "ready"), (time.time()+3600, "ready"), (time.time(), "failed"), ("invalid", "ready"), (True, "ready"), (float("nan"), "ready")])
def test_required_protection_invalid_heartbeat_blocks_all(configuration, gated_app, timestamp, status):
    configuration.FAIL2BAN_REQUIRED = True
    ready(configuration, timestamp, status)
    assert TestClient(gated_app).get("/api/setup/status").status_code == 503


def test_required_missing_protection_blocks_all(configuration, gated_app):
    configuration.FAIL2BAN_REQUIRED = True
    assert TestClient(gated_app).get("/").status_code == 503
    assert not policy.security_status(configuration)["fail2ban"]["active"]


def test_missing_ban_directory_blocks_required_protection(configuration, gated_app):
    configuration.FAIL2BAN_REQUIRED = True
    directory = ready(configuration)
    (directory / "bans").rmdir()
    assert TestClient(gated_app).get("/").status_code == 503


def test_active_ban_blocks_all_requests_and_internal_check(configuration, gated_app):
    configuration.FAIL2BAN_REQUIRED = True
    directory = ready(configuration)
    (directory / "bans" / policy.ban_filename("192.168.1.2")).write_text(json.dumps({"expires_at": time.time()+60}))
    assert TestClient(gated_app, client=("192.168.1.2", 1234)).get("/api/apps", headers={"Cookie": "access_token_cookie=valid"}).status_code == 403
    assert TestClient(gated_app).get("/internal/access", headers={"X-Real-IP": "192.168.1.2"}).status_code == 403


def test_expired_ban_unblocks(configuration, gated_app):
    directory = ready(configuration)
    (directory / "bans" / policy.ban_filename("127.0.0.1")).write_text(json.dumps({"expires_at": time.time()-1}))
    assert TestClient(gated_app).get("/").status_code == 200


@pytest.mark.parametrize("contents", ["{}", '{"expires_at":"forever"}', "{", '{"expires_at":true}', '{"expires_at":NaN}'])
def test_bad_ban_state_never_silently_unblocks(configuration, gated_app, contents):
    directory = ready(configuration)
    (directory / "bans" / policy.ban_filename("127.0.0.1")).write_text(contents)
    assert TestClient(gated_app).get("/").status_code == 503


def test_corrupt_policy_fails_closed(configuration, gated_app):
    from pathlib import Path
    Path(configuration.ACCESS_POLICY_FILE).write_text('{"allow_public":"false"}')
    assert TestClient(gated_app).get("/").status_code == 503


def test_websocket_public_peer_blocked(gated_app):
    with pytest.raises(WebSocketDisconnect) as error:
        with TestClient(gated_app, client=("8.8.8.8", 1234)).websocket_connect("/socket"):
            pass
    assert error.value.code == 1008


def test_websocket_banned_peer_blocked(configuration, gated_app):
    directory = ready(configuration)
    (directory / "bans" / policy.ban_filename("127.0.0.1")).write_text(json.dumps({"expires_at": time.time()+60}))
    with pytest.raises(WebSocketDisconnect) as error:
        with TestClient(gated_app).websocket_connect("/socket"):
            pass
    assert error.value.code == 1008


def test_websocket_protection_loss_closes1013(configuration, gated_app):
    configuration.FAIL2BAN_REQUIRED = True
    with pytest.raises(WebSocketDisconnect) as error:
        with TestClient(gated_app).websocket_connect("/socket"):
            pass
    assert error.value.code == 1013


@pytest.mark.parametrize("change", ["ban", "revoke_public", "protection_loss"])
def test_existing_websocket_stops_forwarding_after_policy_change(configuration, gated_app, change):
    policy.write_access_policy(True, configuration)
    configuration.FAIL2BAN_REQUIRED = True
    directory = ready(configuration)
    peer = "8.8.8.8" if change == "revoke_public" else "192.168.1.2"
    with TestClient(gated_app, client=(peer, 1234)).websocket_connect("/echo") as socket:
        socket.send_text("allowed")
        assert socket.receive_text() == "allowed"
        if change == "ban":
            (directory / "bans" / policy.ban_filename(peer)).write_text(json.dumps({"expires_at": time.time()+60}))
        elif change == "revoke_public":
            policy.write_access_policy(False, configuration)
        else:
            configuration.FAIL2BAN_REQUIRED = True
            (directory / "ready.json").unlink()
        socket.send_text("must not be forwarded")
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_text()
        assert error.value.code == (1013 if change == "protection_loss" else 1008)


@pytest.mark.asyncio
async def test_record_failure_emits_only_canonical_ip_no_username(configuration):
    from pathlib import Path
    db = MagicMock()
    db.commit = AsyncMock()
    await security.record_login_attempt(db, "::ffff:192.168.1.2", "secret-user\ninjected", False)
    line = Path(configuration.SECURITY_LOG).read_text()
    assert "yachtplus-auth failure ip=192.168.1.2\n" in line
    assert "secret-user" not in line
    assert line.count("\n") == 1
    assert db.commit.await_count == 2


@pytest.mark.asyncio
async def test_failure_log_write_error_fails_closed_when_required(configuration, monkeypatch):
    configuration.FAIL2BAN_REQUIRED = True
    monkeypatch.setattr(security, "_append_auth_failure", MagicMock(side_effect=PermissionError()))
    db = MagicMock()
    db.commit = AsyncMock()
    with pytest.raises(HTTPException) as error:
        await security.record_login_attempt(db, "192.168.1.2", "user", False)
    assert error.value.status_code == 503
    assert db.commit.await_count == 2


@pytest.fixture
def admin(monkeypatch):
    user = SimpleNamespace(username="admin", is_active=True)
    monkeypatch.setattr(app_settings, "require_superuser", AsyncMock(return_value=user))
    monkeypatch.setattr(app_settings, "_record_network_access_request", AsyncMock())
    return user


@pytest.mark.asyncio
async def test_setting_public_access_requires_confirmation(configuration, admin):
    with pytest.raises(HTTPException) as error:
        await app_settings.update_security_settings(request("192.168.1.2"), app_settings.NetworkAccessUpdate(allow_public=True), MagicMock(), MagicMock())
    assert error.value.status_code == 422
    assert not policy.read_access_policy(configuration)["allow_public"]


@pytest.mark.asyncio
async def test_public_client_cannot_change_security(configuration, admin):
    policy.write_access_policy(True, configuration)
    with pytest.raises(HTTPException) as error:
        await app_settings.update_security_settings(request("8.8.8.8"), app_settings.NetworkAccessUpdate(allow_public=False), MagicMock(), MagicMock())
    assert error.value.status_code == 403
    assert policy.read_access_policy(configuration)["allow_public"]
    result = await app_settings.get_security_settings(request("8.8.8.8"), MagicMock(), MagicMock())
    assert not result["can_modify"]


@pytest.mark.asyncio
async def test_confirmed_change_persists_and_restrict_can_restore(configuration, admin):
    configuration.FAIL2BAN_REQUIRED = True
    ready(configuration)
    result = await app_settings.update_security_settings(request("192.168.1.2"), app_settings.NetworkAccessUpdate(allow_public=True, confirm_public_access=True), MagicMock(), MagicMock())
    assert result["allow_public"] and result["can_modify"]
    assert policy.read_access_policy(configuration)["allow_public"]
    result = await app_settings.update_security_settings(request("192.168.1.2"), app_settings.NetworkAccessUpdate(allow_public=False), MagicMock(), MagicMock())
    assert not result["allow_public"]


@pytest.mark.asyncio
async def test_public_optin_refused_when_required_protection_unready(configuration, admin):
    configuration.FAIL2BAN_REQUIRED = True
    with pytest.raises(HTTPException) as error:
        await app_settings.update_security_settings(request("192.168.1.2"), app_settings.NetworkAccessUpdate(allow_public=True, confirm_public_access=True), MagicMock(), MagicMock())
    assert error.value.status_code == 503
    assert not policy.read_access_policy(configuration)["allow_public"]


@pytest.mark.asyncio
async def test_security_endpoint_refuses_inactive_admin(configuration, admin):
    admin.is_active = False
    with pytest.raises(HTTPException) as error:
        await app_settings.get_security_settings(request("192.168.1.2"), MagicMock(), MagicMock())
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_public_login_honors_effective_policy(configuration, monkeypatch):
    policy.write_access_policy(True, configuration)
    monkeypatch.setattr(security, "_count_recent_failed_attempts", AsyncMock(return_value=0))
    monkeypatch.setattr(security, "_count_recent_failed_attempts_for_username", AsyncMock(return_value=0))
    assert await security.check_ip_restriction(request("8.8.8.8"), MagicMock(), "user") == "8.8.8.8"


@pytest.mark.asyncio
async def test_nonadmin_cannot_read_or_change_security(configuration, monkeypatch):
    monkeypatch.setattr(app_settings, "require_superuser", AsyncMock(side_effect=HTTPException(403, "Superuser required")))
    with pytest.raises(HTTPException) as error:
        await app_settings.get_security_settings(request("192.168.1.2"), MagicMock(), MagicMock())
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        await app_settings.update_security_settings(request("192.168.1.2"), app_settings.NetworkAccessUpdate(allow_public=True, confirm_public_access=True), MagicMock(), MagicMock())
    assert error.value.status_code == 403
    assert not policy.read_access_policy(configuration)["allow_public"]


@pytest.mark.asyncio
async def test_atomic_policy_write_failure_keeps_previous_policy(configuration, admin, monkeypatch):
    configuration.FAIL2BAN_REQUIRED = True
    ready(configuration)
    policy.write_access_policy(False, configuration)
    monkeypatch.setattr(policy.os, "replace", MagicMock(side_effect=PermissionError()))
    with pytest.raises(HTTPException) as error:
        await app_settings.update_security_settings(request("192.168.1.2"), app_settings.NetworkAccessUpdate(allow_public=True, confirm_public_access=True), MagicMock(), MagicMock())
    assert error.value.status_code == 503
    assert not policy.read_access_policy(configuration)["allow_public"]
    from pathlib import Path
    assert not list(Path(configuration.ACCESS_POLICY_FILE).parent.glob(".access-policy-*"))


@pytest.mark.asyncio
@pytest.mark.parametrize("heartbeat_active", [False, True])
async def test_public_optin_requires_mandatory_fail2ban(configuration, admin, heartbeat_active):
    configuration.FAIL2BAN_REQUIRED = False
    if heartbeat_active:
        ready(configuration)
    with pytest.raises(HTTPException) as error:
        await app_settings.update_security_settings(request("192.168.1.2"), app_settings.NetworkAccessUpdate(allow_public=True, confirm_public_access=True), MagicMock(), MagicMock())
    assert error.value.status_code == 503
    assert not policy.read_access_policy(configuration)["allow_public"]
    app_settings._record_network_access_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabling_public_access_allowed_without_fail2ban(configuration, admin):
    policy.write_access_policy(True, configuration)
    assert not configuration.FAIL2BAN_REQUIRED
    assert not policy.fail2ban_active(configuration)
    result = await app_settings.update_security_settings(request("192.168.1.2"), app_settings.NetworkAccessUpdate(allow_public=False), MagicMock(), MagicMock())
    assert not result["allow_public"]
    assert not policy.read_access_policy(configuration)["allow_public"]


@pytest.mark.parametrize("heartbeat_active", [False, True])
def test_persisted_public_policy_without_mandatory_protection_blocks_public_http(configuration, gated_app, heartbeat_active):
    policy.write_access_policy(True, configuration)
    configuration.FAIL2BAN_REQUIRED = False
    if heartbeat_active:
        ready(configuration)
    public = TestClient(gated_app, client=("8.8.8.8", 1234))
    assert public.get("/api/apps").status_code == 503
    assert public.post("/api/setup/register").status_code == 503
    assert TestClient(gated_app, client=("192.168.1.2", 1234)).get("/").status_code == 200


def test_persisted_public_policy_without_mandatory_protection_blocks_public_websocket(configuration, gated_app):
    policy.write_access_policy(True, configuration)
    ready(configuration)
    configuration.FAIL2BAN_REQUIRED = False
    with pytest.raises(WebSocketDisconnect) as error:
        with TestClient(gated_app, client=("8.8.8.8", 1234)).websocket_connect("/echo"):
            pass
    assert error.value.code == 1013


def test_public_websocket_stops_after_mandatory_protection_disabled(configuration, gated_app):
    policy.write_access_policy(True, configuration)
    configuration.FAIL2BAN_REQUIRED = True
    ready(configuration)
    with TestClient(gated_app, client=("8.8.8.8", 1234)).websocket_connect("/echo") as socket:
        socket.send_text("allowed")
        assert socket.receive_text() == "allowed"
        configuration.FAIL2BAN_REQUIRED = False
        socket.send_text("must not be forwarded")
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_text()
        assert error.value.code == 1013


@pytest.mark.asyncio
async def test_failed_required_audit_preserves_network_policy(configuration, admin, monkeypatch):
    configuration.FAIL2BAN_REQUIRED = True
    ready(configuration)
    policy.write_access_policy(False, configuration)
    monkeypatch.setattr(app_settings, "_record_network_access_request", AsyncMock(side_effect=HTTPException(503, "Security audit unavailable")))
    with pytest.raises(HTTPException) as error:
        await app_settings.update_security_settings(request("192.168.1.2"), app_settings.NetworkAccessUpdate(allow_public=True, confirm_public_access=True), MagicMock(), MagicMock())
    assert error.value.status_code == 503
    assert not policy.read_access_policy(configuration)["allow_public"]


@pytest.mark.asyncio
async def test_network_audit_commit_failure_rolls_back_and_is_reported():
    db = MagicMock()
    db.commit = AsyncMock(side_effect=RuntimeError("DB unavailable"))
    db.rollback = AsyncMock()
    with pytest.raises(HTTPException) as error:
        await app_settings._record_network_access_request(db, "admin", False, True)
    assert error.value.status_code == 503
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_network_change_audit_records_requested_action_before_write(configuration, admin, monkeypatch):
    configuration.FAIL2BAN_REQUIRED = True
    ready(configuration)
    committed_before_mutation = []

    async def acknowledged_audit(db, username, previous, requested):
        committed_before_mutation.append(not policy.read_access_policy(configuration)["allow_public"])

    monkeypatch.setattr(app_settings, "_record_network_access_request", acknowledged_audit)
    result = await app_settings.update_security_settings(request("192.168.1.2"), app_settings.NetworkAccessUpdate(allow_public=True, confirm_public_access=True), MagicMock(), MagicMock())
    assert committed_before_mutation == [True]
    assert result["allow_public"]


@pytest.mark.asyncio
async def test_required_network_audit_uses_attempt_semantics(db):
    from sqlalchemy import select
    from api.db.models.audit import AuditLog
    await app_settings._record_network_access_request(db, "admin", False, True)
    row = (await db.execute(select(AuditLog))).scalars().one()
    assert row.action == "security.network_access.requested"
    assert json.loads(row.details) == {"before": False, "requested": True}


@pytest.mark.asyncio
async def test_successful_authentication_does_not_emit_failure(configuration):
    from pathlib import Path
    db = MagicMock()
    db.commit = AsyncMock()
    await security.record_login_attempt(db, "192.168.1.2", "user", True)
    assert not Path(configuration.SECURITY_LOG).exists()


def test_missing_direct_peer_never_trusts_forwarded_headers(configuration):
    candidate = request("127.0.0.1", {"X-Real-IP": "127.0.0.1"})
    candidate.scope["client"] = None
    assert security._resolve_client_ip(candidate) == "unknown"


def test_malformed_forward_chain_fails_closed(configuration):
    assert security._resolve_client_ip(request("127.0.0.1", {"X-Forwarded-For": "8.8.8.8, not-an-ip"})) == "unknown"


def test_extreme_timestamp_is_invalid_without_overflow():
    assert not policy._timestamp(10**1000)


@pytest.mark.asyncio
async def test_public_optin_does_not_permit_unknown_login_source(configuration):
    policy.write_access_policy(True, configuration)
    with pytest.raises(HTTPException) as error:
        await security.check_ip_restriction(request("testclient"), MagicMock(), "user")
    assert error.value.status_code == 403
