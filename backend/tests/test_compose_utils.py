import pytest
from fastapi import HTTPException
from api.utils.compose import validate_app_name, validate_compose_project_name

def test_validate_app_name_valid():
    assert validate_app_name("my-app") == "my-app"
    assert validate_app_name("app1") == "app1"
    assert validate_app_name("1app") == "1app"

def test_validate_app_name_invalid_injection():
    with pytest.raises(HTTPException) as exc:
        validate_app_name("-flag")
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        validate_app_name("_flag")
    assert exc.value.status_code == 400

def test_validate_compose_project_name_invalid_injection():
    with pytest.raises(HTTPException) as exc:
        validate_compose_project_name("-flag")
    assert exc.value.status_code == 400
