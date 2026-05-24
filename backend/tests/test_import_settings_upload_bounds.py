"""Regression for BUG-006: import_settings handed the uploaded file
straight to `upload.file.read()` inside the CRUD layer with no size or
content-type check. A superuser session could be coerced (or a curious
admin could mistakenly try) into uploading a multi-GB blob, OOM-ing the
worker. The fix bounds the upload at 5 MiB, rejects non-JSON content
types, and rejects non-JSON bodies up front so the CRUD layer never
sees garbage.
"""
import io
import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.database import Base
from api.db.models.users import User
from api.routers.app_settings import import_settings


engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class MockAuth:
    def jwt_required(self, allow_setup_pending=False):
        return True

    def get_jwt_subject(self, allow_setup_pending=False):
        return "root"


@pytest.fixture(autouse=True)
def _force_auth_on(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    s.add(User(username="root", hashed_password="pw", is_superuser=True))
    s.commit()
    yield s
    s.close()


def _upload(data: bytes, content_type: str = "application/json") -> UploadFile:
    up = MagicMock(spec=UploadFile)
    up.content_type = content_type
    up.file = io.BytesIO(data)
    return up


def test_rejects_oversize_upload(db):
    payload = b"a" * (5 * 1024 * 1024 + 1)
    with pytest.raises(HTTPException) as exc:
        import_settings(db=db, upload=_upload(payload), Authorize=MockAuth())
    assert exc.value.status_code == 413


def test_rejects_non_json_content_type(db):
    with pytest.raises(HTTPException) as exc:
        import_settings(
            db=db, upload=_upload(b"{}", content_type="application/zip"),
            Authorize=MockAuth(),
        )
    assert exc.value.status_code == 415


def test_rejects_invalid_utf8(db):
    with pytest.raises(HTTPException) as exc:
        import_settings(db=db, upload=_upload(b"\xff\xfe\xfd"), Authorize=MockAuth())
    # Either the UTF-8 or the JSON check catches this — both are 400.
    assert exc.value.status_code == 400


def test_rejects_malformed_json(db):
    with pytest.raises(HTTPException) as exc:
        import_settings(db=db, upload=_upload(b"not json"), Authorize=MockAuth())
    assert exc.value.status_code == 400


def test_accepts_well_formed_json(db):
    payload = json.dumps({"templates": [], "variables": []}).encode("utf-8")
    with patch("api.routers.app_settings.scrud.import_settings", return_value={"ok": True}) as inner:
        result = import_settings(db=db, upload=_upload(payload), Authorize=MockAuth())
    assert result == {"ok": True}
    # The CRUD layer should see the validated bytes via the re-wrapped stream.
    inner.assert_called_once()
    forwarded_upload = inner.call_args.kwargs["upload"]
    forwarded_upload.file.seek(0)
    assert forwarded_upload.file.read() == payload
