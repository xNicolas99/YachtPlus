"""Regression for BUG-006: import_settings handed the uploaded file
straight to `upload.file.read()` inside the CRUD layer with no size or
content-type check. A superuser session could be coerced (or a curious
admin could mistakenly try) into uploading a multi-GB blob, OOM-ing the
worker. The fix bounds the upload at 5 MiB, rejects non-JSON content
types, and rejects non-JSON bodies up front so the CRUD layer never
sees garbage.

Async migration: the shared conftest `db` fixture now provides an
AsyncSession, and the router + CRUD are async, so every test awaits the
endpoints and uses the async MockAuth.
"""
import io
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException, UploadFile

from api.db.models.users import User
from api.routers.app_settings import import_settings


class MockAuth:
    async def jwt_required(self, allow_setup_pending=False):
        return True

    async def get_jwt_subject(self, allow_setup_pending=False):
        return "root"


@pytest.fixture(autouse=True)
def _force_auth_on(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


async def _seed_superuser(db):
    """The shared conftest `db` fixture starts empty; give it a superuser so
    require_superuser can resolve 'root'."""
    db.add(User(username="root", hashed_password="pw", is_superuser=True))
    await db.commit()


def _upload(data: bytes, content_type: str = "application/json") -> UploadFile:
    up = MagicMock(spec=UploadFile)
    up.content_type = content_type
    up.file = io.BytesIO(data)
    return up


@pytest.mark.asyncio
async def test_rejects_oversize_upload(db):
    await _seed_superuser(db)
    payload = b"a" * (5 * 1024 * 1024 + 1)
    with pytest.raises(HTTPException) as exc:
        await import_settings(db=db, upload=_upload(payload), Authorize=MockAuth())
    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_rejects_non_json_content_type(db):
    await _seed_superuser(db)
    with pytest.raises(HTTPException) as exc:
        await import_settings(
            db=db, upload=_upload(b"{}", content_type="application/zip"),
            Authorize=MockAuth(),
        )
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_rejects_invalid_utf8(db):
    await _seed_superuser(db)
    with pytest.raises(HTTPException) as exc:
        await import_settings(db=db, upload=_upload(b"\xff\xfe\xfd"), Authorize=MockAuth())
    # Either the UTF-8 or the JSON check catches this — both are 400.
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_rejects_malformed_json(db):
    await _seed_superuser(db)
    with pytest.raises(HTTPException) as exc:
        await import_settings(db=db, upload=_upload(b"not json"), Authorize=MockAuth())
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_accepts_well_formed_json(db):
    await _seed_superuser(db)
    payload = json.dumps({"templates": [], "variables": []}).encode("utf-8")
    with patch("api.routers.app_settings.scrud.import_settings", new=AsyncMock(return_value={"ok": True})) as inner:
        result = await import_settings(db=db, upload=_upload(payload), Authorize=MockAuth())
    assert result == {"ok": True}
    # The CRUD layer should see the validated bytes via the re-wrapped stream.
    inner.assert_called_once()
    forwarded_upload = inner.call_args.kwargs["upload"]
    forwarded_upload.file.seek(0)
    assert forwarded_upload.file.read() == payload
