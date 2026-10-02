"""Regression for BUG-008: write_image crashed with TypeError when
image_name was None / "" — `delim in image_tag` raises on a None.
Fix: validate the input up-front and return a clean 422.
"""
import pytest
from fastapi import HTTPException

from api.actions.resources import write_image


@pytest.mark.asyncio
async def test_write_image_rejects_none():
    with pytest.raises(HTTPException) as exc:
        await write_image(None)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_write_image_rejects_empty_string():
    with pytest.raises(HTTPException) as exc:
        await write_image("")
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_write_image_rejects_whitespace_only():
    with pytest.raises(HTTPException) as exc:
        await write_image("   ")
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_write_image_rejects_non_string():
    with pytest.raises(HTTPException) as exc:
        await write_image(12345)  # type: ignore[arg-type]
    assert exc.value.status_code == 422
