import pytest
from api.utils.error_handler import sanitize_error_message

def test_sanitizer_masks_sensitive_fields():
    errors = [
        {"loc": ["body", "password"], "msg": "Field required", "type": "value_error.missing"},
        {"loc": ["body", "username"], "msg": "Field required", "type": "value_error.missing"},
        {"loc": ["body", "2fa_secret"], "msg": "Field required", "type": "value_error.missing"},
        {"loc": ["body", "token"], "msg": "Field required", "type": "value_error.missing"}
    ]

    sanitized = sanitize_error_message(errors)

    # Password should be masked
    assert sanitized[0]["msg"] == "Invalid or missing sensitive field"
    # Username should remain
    assert sanitized[1]["msg"] == "Field required"
    # 2fa_secret should be masked
    assert sanitized[2]["msg"] == "Invalid or missing sensitive field"
    # Token should be masked
    assert sanitized[3]["msg"] == "Invalid or missing sensitive field"

def test_sanitizer_handles_input_field():
    errors = [
        {"loc": ["body", "password"], "msg": "Too short", "input": "secret123"}
    ]
    sanitized = sanitize_error_message(errors)
    assert sanitized[0]["input"] == "***"
    assert sanitized[0]["msg"] == "Invalid or missing sensitive field"
