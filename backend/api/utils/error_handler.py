import logging
import secrets
import traceback
from typing import List, Dict, Any, Optional

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


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


def _new_trace_id() -> str:
    """Return a short, URL-safe request identifier for correlating client
    errors with server logs. Not a security token — just a correlation id.
    """
    return secrets.token_urlsafe(8)


def _client_safe_detail(exc: Exception) -> str:
    """Return a generic, non-revealing message for an unexpected exception.
    Never includes the exception text, SQL, or a stack trace.
    """
    return "An internal error occurred. Please try again later."


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global catch-all for unexpected exceptions.

    Logs the full traceback server-side (with a trace id for correlation) and
    returns only a generic message + trace id to the client, so internal
    details (SQL, stack traces, file paths) never leak.
    """
    trace_id = _new_trace_id()
    logger.error(
        "Unhandled exception trace_id=%s method=%s path=%s",
        trace_id,
        request.method,
        request.url.path,
    )
    logger.error(
        "Unhandled exception trace_id=%s\n%s",
        trace_id,
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": _client_safe_detail(exc), "trace_id": trace_id},
    )


def _mask_sensitive_input(errors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Recursively mask sensitive values in a validation error payload.
    Reuses the SENSITIVE_FIELDS set from sanitize_error_message.
    """
    def _mask(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: ("***" if str(k).lower() in SENSITIVE_FIELDS else _mask(v))
                    for k, v in value.items()}
        if isinstance(value, list):
            return [_mask(v) for v in value]
        return value

    return [_mask(e) for e in errors]


def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle FastAPI RequestValidationError without leaking sensitive input.

    The default handler echoes back the offending `input` value verbatim,
    which can include passwords / tokens / secrets. We sanitise the payload
    before returning it to the client.
    """
    errors = getattr(exc, "errors", lambda: [])()
    sanitized = sanitize_error_message(errors)
    sanitized = _mask_sensitive_input(sanitized)
    return JSONResponse(status_code=422, content={"detail": sanitized})


def docker_error_detail(exc) -> str:
    """Return a client-safe error message for an aiodocker/docker exception.

    The raw exception message may contain daemon paths, internal hostnames,
    or other operational details that should not leave the server. This
    helper preserves the HTTP status via `safe_http_status` but maps the
    message to a small set of generic, still actionable descriptions.
    """
    message = ""
    if hasattr(exc, "message") and exc.message:
        message = exc.message
    elif hasattr(exc, "explanation") and exc.explanation:
        message = exc.explanation
    elif hasattr(exc, "args") and exc.args:
        message = str(exc.args[0])

    lower = message.lower()
    status = safe_http_status(exc, default=500)

    if status == 404 or "no such" in lower or "not found" in lower:
        return "Container or resource not found"
    if status == 409 or "conflict" in lower:
        return "Resource is in a state that prevents this action"
    if "cannot" in lower:
        return "Docker operation could not be completed"
    return "Docker operation failed. Check server logs for details."
