from typing import Any, Dict, List, Union

SENSITIVE_FIELDS = {
    "password", "passwd", "pwd",
    "2fa_secret", "secret",
    "token", "access_token", "refresh_token",
    "api_key", "private_key",
    "ssh_key", "docker_token",
    "email"
}

def sanitize_error_message(error_data: Union[Dict[str, Any], List[Any]]) -> Union[Dict[str, Any], List[Any]]:
    """
    Recursively removes sensitive fields from error response dictionaries/lists.
    """
    if isinstance(error_data, dict):
        sanitized = error_data.copy()
        # Check current level keys
        for key in list(sanitized.keys()):
            # If key itself is sensitive (though unlikely in error structure, but good for input/body)
            if key.lower() in SENSITIVE_FIELDS:
                sanitized[key] = "[REDACTED]"
            # If key is 'input' or 'body', typically contains the request payload
            elif key == "input" or key == "body":
                if isinstance(sanitized[key], dict):
                    sanitized[key] = sanitize_error_message(sanitized[key])
            else:
                # Recurse
                sanitized[key] = sanitize_error_message(sanitized[key])
        return sanitized

    elif isinstance(error_data, list):
        return [sanitize_error_message(item) for item in error_data]

    return error_data
