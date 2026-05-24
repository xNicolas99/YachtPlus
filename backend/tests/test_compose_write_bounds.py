"""Regression for BUG-102: the compose write endpoint sent the user's
`compose.content` straight to disk with no length check. A `perm_restart`
user could fill the compose volume by POSTing an arbitrarily large
string. The fix caps payload at 1 MiB and rejects NUL bytes.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from api.actions.compose import _write_compose_sync, _COMPOSE_MAX_BYTES


def _compose(name="myproj", content=""):
    obj = MagicMock()
    obj.name = name
    obj.content = content
    return obj


@pytest.fixture(autouse=True)
def _stub_validators(monkeypatch):
    # Project-name validation has its own test; stub it so we exercise
    # the content-size branch in isolation.
    monkeypatch.setattr(
        "api.actions.compose.validate_compose_project_name", lambda _n: None
    )


def test_rejects_oversize_payload():
    compose = _compose(content="a" * (_COMPOSE_MAX_BYTES + 1))
    with pytest.raises(HTTPException) as exc:
        _write_compose_sync(compose)
    assert exc.value.status_code == 413


def test_rejects_empty_payload():
    compose = _compose(content="")
    with pytest.raises(HTTPException) as exc:
        _write_compose_sync(compose)
    assert exc.value.status_code == 422


def test_rejects_none_payload():
    compose = _compose(content=None)
    with pytest.raises(HTTPException) as exc:
        _write_compose_sync(compose)
    assert exc.value.status_code == 422


def test_rejects_non_string_payload():
    compose = _compose(content=b"binary blob")
    with pytest.raises(HTTPException) as exc:
        _write_compose_sync(compose)
    assert exc.value.status_code == 422


def test_rejects_nul_bytes():
    compose = _compose(content="version: '3'\x00services:")
    with pytest.raises(HTTPException) as exc:
        _write_compose_sync(compose)
    assert exc.value.status_code == 422


def test_accepts_payload_at_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr("api.actions.compose.settings.COMPOSE_DIR", str(tmp_path) + "/")
    # Stub the post-write read so we don't depend on actual compose parsing.
    monkeypatch.setattr(
        "api.actions.compose._get_compose_sync",
        lambda name: {"name": name, "path": str(tmp_path / name / "docker-compose.yml")},
    )
    payload = "x" * (_COMPOSE_MAX_BYTES)  # exactly at the cap
    compose = _compose(content=payload)
    result = _write_compose_sync(compose)
    assert result["name"] == "myproj"
