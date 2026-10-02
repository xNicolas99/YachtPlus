"""Persistent network policy and fail2ban state shared by HTTP and WebSocket gates.

The fail2ban service is the only writer of protection state. YachtPlus mounts it
read-only and refuses requests when required protection cannot be verified.
"""
import ipaddress
import json
import math
import os
import stat
from pathlib import Path
import tempfile
import time

from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse, Response
from starlette.websockets import WebSocketDisconnect

from api.settings import get_settings

LOCAL_NETWORKS = ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128", "fc00::/7")
_LOCAL_RANGES = tuple(ipaddress.ip_network(value) for value in LOCAL_NETWORKS)


class ProtectionUnavailable(RuntimeError):
    """Security state is missing, stale, unreadable or malformed."""


def canonical_ip(value):
    if not isinstance(value, str) or not value or "%" in value:
        return None
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return str(address)


def is_local_client(value):
    canonical = canonical_ip(value)
    if canonical is None:
        return False
    address = ipaddress.ip_address(canonical)
    return any(address.version == subnet.version and address in subnet for subnet in _LOCAL_RANGES)


def is_usable_client(value):
    canonical = canonical_ip(value)
    if canonical is None:
        return False
    address = ipaddress.ip_address(canonical)
    return is_local_client(canonical) or (address.is_global and not address.is_multicast)


def _read_json(path):
    # Refuse symbolic links and bounded reads prevent malformed state from
    # consuming unlimited memory. Deployments mount protection state read-only.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("State must be a regular file")
        raw = handle.read(65537)
    if len(raw) > 65536:
        raise ValueError("State exceeds size limit")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("State must be an object")
    return data


def read_access_policy(settings=None):
    settings = settings or get_settings()
    path = Path(getattr(settings, "ACCESS_POLICY_FILE", "/config/access-policy.json"))
    try:
        data = _read_json(path)
    except FileNotFoundError:
        # Public access always requires a persisted, explicit opt-in. Legacy
        # YACHT_BLOCK_PUBLIC_IP_LOGIN=false never opens a new installation.
        return {"allow_public": False}
    except (OSError, ValueError, TypeError):
        raise ProtectionUnavailable("Access policy cannot be verified") from None
    if type(data.get("allow_public")) is not bool:
        raise ProtectionUnavailable("Access policy cannot be verified")
    return {"allow_public": data["allow_public"]}


def write_access_policy(allow_public, settings=None):
    if type(allow_public) is not bool:
        raise ValueError("allow_public must be boolean")
    settings = settings or get_settings()
    destination = Path(getattr(settings, "ACCESS_POLICY_FILE", "/config/access-policy.json"))
    temporary = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix=".access-policy-", dir=destination.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.chmod(temporary, 0o600)
            json.dump({"allow_public": allow_public}, handle)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        # Each change is a complete boolean assignment; atomic replacement
        # makes concurrent workers observe either complete old or new policy.
        os.replace(temporary, destination)
    except OSError:
        raise ProtectionUnavailable("Access policy could not be saved") from None
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def _timestamp(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def fail2ban_active(settings=None, now=None):
    settings = settings or get_settings()
    now = time.time() if now is None else now
    directory = Path(getattr(settings, "FAIL2BAN_STATE_DIR", "/run/yachtplus-security"))
    try:
        heartbeat = _read_json(directory / "ready.json")
        timestamp = heartbeat.get("timestamp")
        return heartbeat.get("status") == "ready" and _timestamp(timestamp) and 0 <= now - timestamp <= 30
    except (OSError, ValueError, TypeError):
        return False


def ban_filename(client_ip):
    canonical = canonical_ip(client_ip)
    if canonical is None:
        raise ValueError("Invalid client IP")
    # Colons are illegal in Windows filenames; canonicalisation and replacing
    # colons preserve distinct IPv6 addresses without permitting traversal.
    return canonical.replace(":", "_") + ".json"


def check_protection(client_ip, settings=None, now=None):
    settings = settings or get_settings()
    now = time.time() if now is None else now
    required = getattr(settings, "FAIL2BAN_REQUIRED", False)
    active = fail2ban_active(settings, now)
    if required and not active:
        raise ProtectionUnavailable("Fail2ban protection is unavailable")
    directory = Path(getattr(settings, "FAIL2BAN_STATE_DIR", "/run/yachtplus-security"))
    try:
        ban = _read_json(directory / "bans" / ban_filename(client_ip))
    except FileNotFoundError:
        if required and not (directory / "bans").is_dir():
            raise ProtectionUnavailable("IP protection state cannot be verified") from None
        return False
    except (OSError, ValueError, TypeError):
        raise ProtectionUnavailable("IP protection state cannot be verified") from None
    expiry = ban.get("expires_at")
    if not _timestamp(expiry):
        raise ProtectionUnavailable("IP protection state cannot be verified")
    return expiry > now


def security_status(settings=None):
    settings = settings or get_settings()
    return {
        **read_access_policy(settings),
        "local_networks": list(LOCAL_NETWORKS),
        "fail2ban": {"required": getattr(settings, "FAIL2BAN_REQUIRED", False), "active": fail2ban_active(settings)},
        "public_access_requires_confirmation": True,
        "changes_require_local_client": True,
    }


def client_access_allowed(client_ip, settings):
    policy = read_access_policy(settings)
    if is_local_client(client_ip):
        return True
    if not policy["allow_public"]:
        return False
    # A policy persisted while protection was mandatory must not silently
    # open public access after an operator disables the requirement later.
    # LAN access remains available so an administrator can revoke the opt-in.
    if not getattr(settings, "FAIL2BAN_REQUIRED", False):
        raise ProtectionUnavailable("Public access requires mandatory fail2ban")
    return True


class AccessPolicyMiddleware:
    """Outermost ASGI gate, including unauthenticated setup and WebSockets."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        # Lazy import avoids the security/access-policy module cycle.
        from api.utils.security import _resolve_client_ip, _is_trusted_proxy
        request = HTTPConnection(scope)
        client_ip = _resolve_client_ip(request)
        internal = scope.get("path") == "/internal/access"
        peer = canonical_ip(request.client.host) if request.client else None
        if internal and (
            scope["type"] != "http" or scope.get("method") != "GET"
            or peer not in ("127.0.0.1", "::1")
            or not request.headers.get("x-real-ip")
            or not _is_trusted_proxy(peer)
            or canonical_ip(request.headers.get("x-real-ip")) is None
        ):
            return await self._deny(scope, receive, send, 403, "Internal endpoint")
        if not is_usable_client(client_ip):
            return await self._deny(scope, receive, send, 403, "Invalid client address")
        try:
            settings = get_settings()
            if not client_access_allowed(client_ip, settings):
                return await self._deny(scope, receive, send, 403, "Access restricted to local networks")
            if check_protection(client_ip, settings):
                return await self._deny(scope, receive, send, 403, "IP temporarily blocked")
        except ProtectionUnavailable:
            return await self._deny(scope, receive, send, 503, "Security protection unavailable")
        if internal:
            return await Response(status_code=204)(scope, receive, send)
        if scope["type"] == "websocket":
            return await self._guard_websocket(scope, receive, send, client_ip, settings)
        await self.app(scope, receive, send)

    async def _guard_websocket(self, scope, receive, send, client_ip, settings):
        closed = False

        async def guard():
            nonlocal closed
            if closed:
                return 1008
            code = None
            try:
                if not client_access_allowed(client_ip, settings):
                    code = 1008
                elif check_protection(client_ip, settings):
                    code = 1008
            except ProtectionUnavailable:
                code = 1013
            if code:
                closed = True
                await send({"type": "websocket.close", "code": code, "reason": "Security policy changed"})
            return code

        async def guarded_receive():
            message = await receive()
            if message["type"] == "websocket.disconnect":
                return message
            code = await guard()
            return {"type": "websocket.disconnect", "code": code} if code else message

        async def guarded_send(message):
            nonlocal closed
            if message["type"] == "websocket.close":
                if not closed:
                    closed = True
                    await send(message)
                return
            code = await guard()
            if code:
                raise WebSocketDisconnect(code)
            await send(message)

        try:
            await self.app(scope, guarded_receive, guarded_send)
        except WebSocketDisconnect:
            # The gate itself has already delivered the close frame.
            if not closed:
                raise

    @staticmethod
    async def _deny(scope, receive, send, code, detail):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1013 if code == 503 else 1008, "reason": detail})
        else:
            await JSONResponse({"detail": detail}, status_code=code)(scope, receive, send)
