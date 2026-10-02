"""Cookie mutation and WebSocket origin protection."""
import secrets
from urllib.parse import urlsplit
from starlette.responses import JSONResponse

def same_origin(scope):
    headers = dict(scope.get("headers", []))
    origin = headers.get(b"origin")
    if not origin:
        return True
    try:
        from api.utils.security import _is_trusted_proxy
        peer = (scope.get("client") or (None,))[0]
        scheme = scope.get("scheme", "http").replace("ws", "http")
        if _is_trusted_proxy(peer):
            scheme = headers.get(b"x-forwarded-proto", scheme.encode()).decode().split(",")[0].strip()
        expected = urlsplit(scheme + "://" + headers.get(b"host", b"").decode())
        actual = urlsplit(origin.decode())
        def identity(url):
            return (url.scheme, url.hostname, url.port or (443 if url.scheme == "https" else 80))
        return (actual.scheme in {"http", "https"} and not actual.username and
                not actual.password and actual.path in {"", "/"} and not actual.query and
                not actual.fragment and identity(actual) == identity(expected))
    except (ValueError, UnicodeError):
        return False

class CSRFProtectionMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        from starlette.requests import Request
        if scope["type"] == "websocket":
            from api.main import _host_allowed
            headers = dict(scope.get("headers", []))
            if not _host_allowed(headers.get(b"host", b"").decode()) or not same_origin(scope):
                await send({"type": "websocket.close", "code": 1008})
                return
        elif scope["type"] == "http" and scope.get("method") not in {"GET", "HEAD", "OPTIONS"}:
            request = Request(scope)
            bearer = request.headers.get("authorization", "").startswith("Bearer ")
            forbidden = not same_origin(scope)
            public_credentials = scope.get("path") in {"/api/auth/login", "/api/auth/login_cookie", "/api/setup/register"}
            if request.cookies.get("access_token_cookie") and not bearer and not public_credentials:
                cookie = request.cookies.get("csrf_access_token", "")
                header = request.headers.get("x-csrf-token", "")
                forbidden = forbidden or not cookie or not secrets.compare_digest(cookie, header)
            if forbidden:
                await JSONResponse({"detail": "CSRF validation failed"}, status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)
