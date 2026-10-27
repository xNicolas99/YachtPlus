import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator
from api.utils.error_handler import sanitize_error_message, validation_exception_handler


class ValidationPayload(BaseModel):
    count: int

    @field_validator("count")
    @classmethod
    def positive_count(cls, value):
        if value < 0:
            raise ValueError("Count must be positive")
        return value


@pytest.fixture
def validation_client():
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    @app.post("/validate")
    def validate(payload: ValidationPayload):
        return payload

    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b'{"count": -1}', "application/json"),
        (b'{"count": NaN}', "application/json"),
        (b'{"count": Infinity}', "application/json"),
        (b"invalid body", "application/octet-stream"),
        (b"\xff", "application/octet-stream"),
    ],
)
def test_validation_handler_returns_422_for_non_json_error_values(validation_client, body, content_type):
    response = validation_client.post("/validate", content=body, headers={"Content-Type": content_type})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] in (["body"], ["body", "count"])


def test_validation_handler_redacts_nested_secrets_before_encoding(validation_client):
    response = validation_client.post("/validate", json={
        "password": "private-password",
        "nested": {"token": "private-token"},
        "items": [{"api_key": "private-api-key"}],
    })

    assert response.status_code == 422
    assert "private-" not in response.text
    assert response.json()["detail"][0]["input"] == {
        "password": "***", "nested": {"token": "***"}, "items": [{"api_key": "***"}],
    }


def test_validation_handler_masks_raw_body_with_wrong_content_type(validation_client):
    response = validation_client.post(
        "/validate",
        content=b'{"password":"redaction-test-sentinel"}',
        headers={"Content-Type": "application/octet-stream"},
    )

    assert response.status_code == 422
    assert "redaction-test-sentinel" not in response.text
    assert response.json()["detail"][0]["input"] == "***"

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
