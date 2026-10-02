"""Regression cases for the submitted 117-point error report."""
import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pyotp
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from starlette.requests import Request
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from sqlalchemy import select

from api.auth.jwt import AuthWrapper, TokenData, account_claims, create_access_token, validate_account
from api.db.crud import users, templates
from api.db.models.users import User, APIKEY
from api.db.models.settings import TokenBlacklist, SMTPSettings
from api.db.schemas.users import UserCreate, UserSelfUpdate, UserUpdate


@pytest_asyncio.fixture
async def account_db(db, monkeypatch):
    @asynccontextmanager
    async def sessions():
        yield db
    monkeypatch.setattr("api.db.database.SessionLocal", sessions)
    monkeypatch.setattr("api.auth.jwt.settings.DISABLE_AUTH", False)
    return db


async def add_user(db, name="operator", **values):
    user = User(username=name, hashed_password="unused", is_active=True, **values)
    db.add(user)
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_credentials_never_transfer_to_recreated_username(account_db):
    original = await add_user(account_db)
    data = TokenData(username=original.username, auth_version=original.auth_version)
    await account_db.delete(original)
    await account_db.commit()
    replacement = await add_user(account_db)
    assert replacement.auth_version != data.auth_version
    with pytest.raises(HTTPException) as exc:
        await validate_account(data)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_disabled_account_and_legacy_token_are_rejected(account_db):
    user = await add_user(account_db)
    with pytest.raises(HTTPException):
        await validate_account(TokenData(username=user.username))
    user.is_active = False
    await account_db.commit()
    with pytest.raises(HTTPException):
        await validate_account(TokenData(username=user.username, auth_version=user.auth_version))


@pytest.mark.asyncio
@pytest.mark.parametrize("path,method", [("/api/auth/refresh", "POST"), ("/api/auth/me", "POST"),
    ("/api/auth/api/keys/new", "POST"), ("/api/auth/2fa/generate", "POST"),
    ("/api/compose/demo/actions/pull", "POST"), ("/api/containers/abc/start", "POST"),
    ("/api/apps/deploy", "POST"), ("/api/auth/me", "GET")])
async def test_api_keys_cannot_mutate_or_access_account_credentials(account_db, path, method):
    user = await add_user(account_db)
    key = await users.create_key("automation", user, None, account_db)
    request = Request({"type": "http", "method": method, "path": path, "headers": [(b"authorization", ("Bearer " + key["token"]).encode())]})
    with pytest.raises(HTTPException) as exc:
        await AuthWrapper(request).jwt_required()
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_api_key_can_read_data_with_active_account(account_db):
    user = await add_user(account_db)
    key = await users.create_key("automation", user, None, account_db)
    request = Request({"type": "http", "method": "GET", "path": "/api/apps/", "headers": [(b"authorization", ("Bearer " + key["token"]).encode())]})
    assert (await AuthWrapper(request).jwt_required()).username == user.username


@pytest.mark.asyncio
async def test_permissions_are_saved_on_create_and_edit(account_db):
    user = await users.create_user(account_db, UserCreate(username="worker", password="pw", perm_start=True, perm_restart=True))
    assert user.perm_start and user.perm_restart
    old_version = user.auth_version
    user = await users.update_user_by_id(account_db, user.id, UserUpdate(perm_restart=False, perm_delete=True))
    assert not user.perm_restart and user.perm_delete
    assert old_version != user.auth_version


@pytest.mark.asyncio
async def test_password_change_requires_current_password_and_revokes_credentials(account_db):
    user = await add_user(account_db)
    user.hashed_password = await users.get_password_hash("current")
    await account_db.commit()
    data = TokenData(username=user.username, auth_version=user.auth_version)
    with pytest.raises(HTTPException):
        await users.update_user(account_db, UserSelfUpdate(password="new"), user.username)
    await users.update_user(account_db, UserSelfUpdate(password="new", current_password="current"), user.username)
    assert await users.verify_password("new", user.hashed_password)
    with pytest.raises(HTTPException):
        await validate_account(data)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [dict(is_active=False), dict(is_superuser=False)])
async def test_last_active_admin_cannot_be_disabled_or_demoted(account_db, change):
    admin = await add_user(account_db, "admin", is_superuser=True)
    inactive = User(username="inactive", hashed_password="unused", is_superuser=True, is_active=False)
    account_db.add(inactive)
    await account_db.commit()
    with pytest.raises(HTTPException) as exc:
        await users.update_user_by_id(account_db, admin.id, UserUpdate(**change))
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_self_demotion_rejected_even_with_other_admin(account_db):
    admin = await add_user(account_db, "admin", is_superuser=True)
    await add_user(account_db, "other", is_superuser=True)
    with pytest.raises(HTTPException):
        await users.update_user_by_id(account_db, admin.id, UserUpdate(is_superuser=False), requesting_user_id=admin.id)


@pytest.mark.asyncio
async def test_revoked_api_key_can_still_be_deleted(account_db):
    user = await add_user(account_db)
    key = await users.create_key("automation", user, None, account_db)
    account_db.add(TokenBlacklist(jti=key["jti"], revoked=True))
    await account_db.commit()
    await users.blacklist_api_key(key["id"], account_db, user)
    assert await account_db.get(APIKEY, key["id"]) is None


@pytest.mark.asyncio
async def test_blacklist_database_failure_fails_closed(monkeypatch):
    from api.auth.jwt import _is_jti_revoked, revoke_token
    @asynccontextmanager
    async def broken():
        raise OSError("database unavailable")
        yield
    monkeypatch.setattr("api.db.database.SessionLocal", broken)
    with pytest.raises(HTTPException) as exc:
        await _is_jti_revoked("credential")
    assert exc.value.status_code == 503
    with pytest.raises(Exception):
        await revoke_token(create_access_token({"sub": "operator"}))


@pytest.mark.asyncio
async def test_refresh_token_can_only_be_consumed_once(account_db):
    from api.auth.jwt import revoke_token
    token = create_access_token({"sub": "operator"})
    await revoke_token(token, require_new=True)
    with pytest.raises(HTTPException) as exc:
        await revoke_token(token, require_new=True)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_totp_code_cannot_be_replayed(account_db):
    from api.utils.crypto import encrypt
    from api.utils.totp import consume_totp
    user = await add_user(account_db)
    secret = pyotp.random_base32()
    user.otp_secret = encrypt(secret)
    await account_db.commit()
    code = pyotp.TOTP(secret).now()
    assert await consume_totp(account_db, user, code)
    assert not await consume_totp(account_db, user, code)


@pytest.mark.asyncio
async def test_active_2fa_secret_cannot_be_overwritten(account_db):
    from api.routers.auth_2fa import generate_2fa_logic
    user = await add_user(account_db, is_2fa_enabled=True, otp_secret="existing")
    auth = SimpleNamespace(jwt_required=AsyncMock(), get_jwt_subject=AsyncMock(return_value=user.username))
    with pytest.raises(HTTPException) as exc:
        await generate_2fa_logic(account_db, auth)
    assert exc.value.status_code == 409
    assert user.otp_secret == "existing"


@pytest.mark.parametrize("headers,status", [({},403), ({"X-CSRF-TOKEN":"proof"},200),
    ({"X-CSRF-TOKEN":"wrong"},403), ({"X-CSRF-TOKEN":"proof", "Origin":"http://testserver:9000"},403),
    ({"X-CSRF-TOKEN":"proof", "Origin":"http://testserver"},200)])
def test_cookie_mutations_require_csrf_and_exact_origin(headers,status):
    from api.utils.csrf import CSRFProtectionMiddleware
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    @app.post("/change")
    async def change():
        return {"success": True}
    with TestClient(app) as client:
        client.cookies.set("access_token_cookie", "session")
        client.cookies.set("csrf_access_token", "proof")
        assert client.post("/change", headers=headers).status_code == status


def test_websocket_rejects_other_port_and_invalid_host():
    from api.utils.csrf import CSRFProtectionMiddleware
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    @app.websocket("/shell")
    async def shell(ws):
        await ws.accept()
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/shell", headers={"Origin": "http://testserver:9000"}):
                pass


@pytest.mark.parametrize("ip", ["100.64.0.1", "100.127.255.254", "64:ff9b::a00:1", "::ffff:127.0.0.1"])
def test_template_fetch_blocks_special_networks(ip):
    assert templates.is_private_ip(ip)


def test_connect_uses_validated_address_without_third_dns_resolution(monkeypatch):
    import socket
    lookup = MagicMock(return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,"",("93.184.216.34",80))])
    sock = MagicMock()
    monkeypatch.setattr(templates.socket, "getaddrinfo", lookup)
    monkeypatch.setattr(templates.socket, "socket", MagicMock(return_value=sock))
    connection = templates._SSRFGuardedHTTPConnection("catalog.example",80,timeout=1)
    connection.connect()
    lookup.assert_called_once()
    sock.connect.assert_called_once_with(("93.184.216.34",80))


@pytest.mark.parametrize("content", ["a: &a [1]\nb: *a", "a: ["*60 + "1" + "]"*60])
def test_yaml_aliases_and_excessive_depth_rejected(content):
    from api.utils.yaml_loader import load_yaml
    with pytest.raises(HTTPException):
        load_yaml(content)


def test_portainer_v2_catalog_and_all_labeled_ports_are_imported():
    payload = {"version":"2", "templates":[{"title":"Web", "image":"nginx", "command":"nginx -g 'daemon off;'", "ports":[{"web":"80:80/tcp"},{"tls":"443:443/tcp"}]}]}
    item = templates._items_from_payload(payload)[0]
    assert item.command == ["nginx", "-g", "daemon off;"]
    assert len(item.ports) == 2


@pytest.mark.asyncio
async def test_template_refresh_eager_loads_and_resets_ports(account_db, monkeypatch):
    from api.db.models.containers import Template
    template = Template(title="Catalog", url="https://catalog.example/catalog.json")
    account_db.add(template)
    await account_db.commit()
    monkeypatch.setattr(templates, "_fetch_template_payload", AsyncMock(return_value={"templates":[
        {"title":"First","ports":["80/tcp"]},{"title":"Second"}]}))
    refreshed = await templates.refresh_template(account_db,template.id)
    assert len(refreshed.items)==2 and refreshed.items[1].ports==[]
    template_id = template.id
    account_db.expire_all()
    loaded = await templates.get_template_by_id(account_db,template_id)
    assert len(loaded.items)==2


@pytest.mark.parametrize("body,status", [(b"x"*100,413), (b"a: &a [1]\nb: *a",422)])
def test_remote_template_payload_is_bounded(body,status,monkeypatch):
    opener=MagicMock()
    response=MagicMock()
    response.__enter__.return_value=response
    response.read1.side_effect=[body,b""]
    opener.open.return_value=response
    monkeypatch.setattr(templates,"validate_url",lambda _:True)
    monkeypatch.setattr(templates,"_build_safe_opener",lambda:opener)
    monkeypatch.setattr(templates,"TEMPLATE_MAX_BYTES",50)
    with pytest.raises(HTTPException) as exc:
        templates._fetch_template_payload_sync("https://catalog.example/catalog.yaml")
    assert exc.value.status_code==status


def test_compose_environment_has_no_server_secrets(monkeypatch):
    from api.actions.compose import _compose_environment
    monkeypatch.setenv("SECRET_KEY","must-never-reach-compose")
    monkeypatch.setenv("DATABASE_URL","private-db")
    environment=_compose_environment()
    assert "SECRET_KEY" not in environment and "DATABASE_URL" not in environment


def test_compose_catalog_skips_invalid_yaml_and_omits_environment(tmp_path,monkeypatch):
    from api.actions.compose import _get_compose_projects_sync
    for name,content in {"good":"services:\n  web:\n    image: nginx\n    environment:\n      PASSWORD: secret", "bad":"[1,2]"}.items():
        directory=tmp_path/name
        directory.mkdir()
        (directory/"compose.yaml").write_text(content)
    monkeypatch.setattr("api.actions.compose.get_settings",lambda:SimpleNamespace(COMPOSE_DIR=str(tmp_path)))
    projects=_get_compose_projects_sync()
    assert len(projects)==1
    assert "secret" not in json.dumps(projects)


def test_compose_down_failure_preserves_project_files(tmp_path,monkeypatch):
    from api.actions.compose import _delete_compose_sync
    directory=tmp_path/"demo"
    directory.mkdir()
    (directory/"compose.yaml").write_text("services: {web: {image: nginx}}")
    monkeypatch.setattr("api.actions.compose.get_settings",lambda:SimpleNamespace(COMPOSE_DIR=str(tmp_path),DOCKER_HOST=None))
    def fail(*args):
        raise HTTPException(400,"down failed")
    monkeypatch.setattr("api.actions.compose._run_compose_command",fail)
    with pytest.raises(HTTPException):
        _delete_compose_sync("demo")
    assert directory.exists()


def test_compose_auto_update_requires_explicit_opt_in(monkeypatch):
    from api.services import watchtower
    monkeypatch.setattr(watchtower,"get_settings",lambda:SimpleNamespace(COMPOSE_AUTO_UPDATE=False))
    update=MagicMock()
    monkeypatch.setattr(watchtower,"update_compose_project",update)
    watchtower.update_all_projects()
    update.assert_not_called()


def test_memory_subtracts_cgroup_cache():
    from api.utils.container_stats import memory_usage
    assert memory_usage({"usage":100,"stats":{"inactive_file":30}})==70
    assert memory_usage({"usage":100,"stats":{"total_inactive_file":20}})==80


@pytest.mark.asyncio
async def test_smtp_password_encrypted_and_never_returned(account_db,monkeypatch):
    from api.routers import smtp
    from api.utils.crypto import decrypt
    monkeypatch.setattr(smtp,"require_superuser",AsyncMock())
    result=await smtp.update_smtp_settings(smtp.SMTPSettingsSchema(server="mail.example",port=587,password="secret",sender_email="admin@example.com"),account_db,None)
    row=(await account_db.execute(select(SMTPSettings))).scalars().first()
    assert row.password.startswith("v2:") and decrypt(row.password)=="secret"
    assert result.password is None and result.password_configured
    await smtp.update_smtp_settings(smtp.SMTPSettingsSchema(server="mail.example",port=587,password=None,sender_email="admin@example.com"),account_db,None)
    assert decrypt(row.password)=="secret"


def test_persistent_secret_creation_converges_and_empty_files_fail(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from api.utils.secret_files import read_or_create_secret
    path=tmp_path/"salt"
    with ThreadPoolExecutor(max_workers=4) as executor:
        values=list(executor.map(lambda _:read_or_create_secret(path,__import__("secrets").token_bytes,16),range(12)))
    assert len(set(values))==1
    path.write_bytes(b"")
    with pytest.raises(RuntimeError):
        read_or_create_secret(path,lambda:b"x"*16,16)


@pytest.mark.asyncio
async def test_terminal_stream_resize_input_and_disconnect(monkeypatch):
    from api.routers import containers
    from starlette.websockets import WebSocketDisconnect
    from aiodocker.stream import Message
    monkeypatch.setattr(containers.settings,"DISABLE_AUTH",True)
    monkeypatch.setattr(containers,"log_activity",AsyncMock())
    monkeypatch.setattr(containers,"SessionLocal",lambda:SimpleNamespace(close=AsyncMock()))
    output_started=False
    async def output():
        nonlocal output_started
        if not output_started:
            output_started=True
            return Message(1,b"ready")
        await asyncio.Event().wait()
    stream=SimpleNamespace(read_out=AsyncMock(side_effect=output),write_in=AsyncMock(),close=AsyncMock())
    execution=SimpleNamespace(id="exec-id",start=MagicMock(return_value=stream),resize=AsyncMock())
    container=SimpleNamespace(exec=AsyncMock(return_value=execution))
    docker=SimpleNamespace(containers=SimpleNamespace(get=AsyncMock(return_value=container)),close=AsyncMock())
    monkeypatch.setattr(containers.aiodocker,"Docker",lambda **_:docker)
    ws=SimpleNamespace(accept=AsyncMock(),cookies={},send_json=AsyncMock(),send_bytes=AsyncMock(),close=AsyncMock(),
        receive_text=AsyncMock(side_effect=['{"type":"resize","cols":120,"rows":40}',"echo hello\r",WebSocketDisconnect()]))
    await asyncio.wait_for(containers.container_exec_websocket(ws,"abc",shell="/bin/sh"),2)
    container.exec.assert_awaited_once_with(cmd=["/bin/sh","-i","-l"],stdin=True,stdout=True,stderr=True,tty=True)
    execution.resize.assert_awaited_once_with(h=40,w=120)
    stream.write_in.assert_awaited_once_with(b"echo hello\r")
    stream.close.assert_awaited_once()
    docker.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_last_admin_deletions_leave_one_admin(tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
    from api.db.database import Base
    engine=create_async_engine("sqlite+aiosqlite:///"+str(tmp_path/"race.db"))
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            first=await add_user(db,"first",is_superuser=True)
            second=await add_user(db,"second",is_superuser=True)
            ids=[first.id,second.id]
        async def remove(user_id):
            async with sessions() as db:
                try:
                    await users.delete_user(db,user_id)
                    return "deleted"
                except HTTPException as exc:
                    return exc.status_code
        results=await asyncio.gather(*(remove(user_id) for user_id in ids))
        assert sorted(results,key=str)==[400,"deleted"]
        async with sessions() as db:
            assert len((await db.execute(select(User))).scalars().all())==1
    finally:
        await engine.dispose()


def test_smtp_tls_verifies_certificates_and_supports_smtps(monkeypatch):
    import ssl
    from api.utils import smtp_delivery
    smtp=MagicMock()
    secure=MagicMock()
    monkeypatch.setattr(smtp_delivery.smtplib,"SMTP",smtp)
    monkeypatch.setattr(smtp_delivery.smtplib,"SMTP_SSL",secure)
    settings=SimpleNamespace(server="mail.example",port=587,use_tls=True,username=None,password=None,sender_email="admin@example.com")
    smtp_delivery.deliver(settings,"admin@example.com",SimpleNamespace(as_string=lambda:"message"))
    context=smtp.return_value.starttls.call_args.kwargs["context"]
    assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
    assert smtp.call_args.kwargs["timeout"]==10
    smtp.return_value.quit.assert_called_once()
    settings.port=465
    smtp_delivery.deliver(settings,"admin@example.com",SimpleNamespace(as_string=lambda:"message"))
    assert secure.call_args.kwargs["context"].check_hostname
    secure.return_value.quit.assert_called_once()
