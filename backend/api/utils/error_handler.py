from typing import List, Dict, Any


def safe_http_status(exc, default: int = 503) -> int:
    """Clamp a docker-library exception's `.status` (or `.status_code`)
    to a valid HTTP status code.

    aiodocker raises `DockerError(900, …)` as a sentinel meaning "couldn't
    even reach the daemon" (Temporary failure in name resolution / refused
    connection / etc.). Forwarding 900 as `HTTPException(status_code=…)`
    crashes uvicorn with `KeyError: 900` when it tries to render the
    status line — 900 isn't in the HTTP status table. Anything outside
    400-599 collapses to `default` (503 = Service Unavailable, which
    matches the situation: request is fine, upstream is down).
    """
    raw = getattr(exc, "status", None)
    if raw is None:
        raw = getattr(exc, "status_code", None)
    try:
        code = int(raw)
    except (TypeError, ValueError):
        return default
    if 400 <= code <= 599:
        return code
    return default

SENSITIVE_FIELDS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "secret",
    "2fa_secret",
    "otp_token",
    "two_fa_secret"
}

def sanitize_error_message(errors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sanitizes validation errors by removing sensitive fields from the output.
    Returns a generic message for sensitive fields.
    """
    sanitized = []
    for error in errors:
        new_error = error.copy()

        # Check location (body, query, etc.)
        loc = new_error.get("loc", [])

        # Check if any part of the location path matches a sensitive field
        is_sensitive = False
        for field in loc:
            if isinstance(field, str) and field.lower() in SENSITIVE_FIELDS:
                is_sensitive = True
                break

        if is_sensitive:
            # Replace detail with generic message and mask input
            new_error["msg"] = "Invalid or missing sensitive field"
            if "input" in new_error:
                new_error["input"] = "***"
            if "ctx" in new_error:
                 new_error.pop("ctx", None)

        sanitized.append(new_error)

    return sanitized
