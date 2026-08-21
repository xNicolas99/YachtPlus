"""Regression for BUG-014: delete_container forwarded its path parameter
verbatim into the aiodocker URL builder. Even though aiodocker URL-encodes
path components, accepting an unbounded string for `container_id` is a
defense-in-depth gap — a hostile or buggy caller could pass strings with
leading dashes/slashes that confuse downstream tooling. The fix validates
against Docker's container-name/ID regex before issuing any docker call.
"""
import pytest
from fastapi import HTTPException

from api.routers.containers import _validate_container_id


def test_accepts_short_hex_id():
    assert _validate_container_id("a1b2c3d4e5f6") == "a1b2c3d4e5f6"


def test_accepts_full_64char_hex():
    cid = "a" * 64
    assert _validate_container_id(cid) == cid


def test_accepts_dotted_name():
    assert _validate_container_id("my.compose.svc-1") == "my.compose.svc-1"


def test_rejects_empty():
    with pytest.raises(HTTPException) as exc:
        _validate_container_id("")
    assert exc.value.status_code == 400


def test_rejects_leading_dash():
    # `-rf` would look like a CLI flag to anything that ever shells out.
    with pytest.raises(HTTPException):
        _validate_container_id("-rf")


def test_rejects_slash():
    with pytest.raises(HTTPException):
        _validate_container_id("foo/bar")


def test_rejects_whitespace():
    with pytest.raises(HTTPException):
        _validate_container_id("foo bar")


def test_rejects_url_encoded_path():
    with pytest.raises(HTTPException):
        _validate_container_id("foo%2Fbar")


def test_rejects_oversize():
    with pytest.raises(HTTPException):
        _validate_container_id("a" * 256)


def test_rejects_non_string():
    with pytest.raises(HTTPException):
        _validate_container_id(None)  # type: ignore[arg-type]
