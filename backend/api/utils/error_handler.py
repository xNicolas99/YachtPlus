from typing import List, Dict, Any

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
