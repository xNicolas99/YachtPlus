"""Regression for the bundled-catalog seed + upload / manual / edit
endpoints. These three input methods let the operator install a
catalog without depending on a public HTTP feed:

  1. configs/*.json shipped in the image (loaded on setup-finalize),
  2. POST /api/templates/upload   (multipart file from the UI),
  3. POST /api/templates/manual + PUT /api/templates/{id}/content
     (paste JSON in the textarea, edit later).

Every catalog created this way gets a synthetic `local://...` URL so
the existing unique-on-url constraint still holds and /refresh cleanly
errors instead of trying to fetch a non-existent feed.
"""
import io
import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.users import User
from api.db.models.containers import Template, TemplateItem
from api.db.crud import templates as crud
from api.routers.templates import (
    upload_template,
    create_manual_template,
    edit_template_content,
    ManualTemplateBody,
    EditTemplateBody,
)


class MockAuth:
    async def jwt_required(self, allow_setup_pending=False):
        return True

    async def get_jwt_subject(self, allow_setup_pending=False):
        return "root"


@pytest.fixture(autouse=True)
def _force_auth_on(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


async def _add_superuser(db: AsyncSession) -> User:
    """conftest's `db` fixture starts empty — router endpoints (which call
    `_require_superuser`) look up the authenticated user by name, so seed a
    `root` superuser for those tests."""
    user = User(username="root", hashed_password="pw", is_superuser=True)
    db.add(user)
    await db.commit()
    return user


async def _count(db: AsyncSession, model) -> int:
    result = await db.execute(select(model))
    return len(result.scalars().all())


# --- crud.add_template_from_payload ----------------------------------------

@pytest.mark.asyncio
async def test_add_template_from_payload_accepts_list(db):
    payload = [
        {"type": 1, "title": "Nginx", "image": "nginx:latest", "platform": "linux"},
        {"type": 1, "title": "Redis", "image": "redis:7", "platform": "linux"},
    ]
    t = await crud.add_template_from_payload(db, "Test", payload)
    assert t is not None
    assert t.title == "Test"
    assert t.url.startswith("local://")
    result = await db.execute(
        select(TemplateItem).filter(TemplateItem.template_id == t.id)
    )
    items = result.scalars().all()
    assert len(items) == 2


@pytest.mark.asyncio
async def test_add_template_from_payload_rejects_empty(db):
    with pytest.raises(HTTPException) as exc:
        await crud.add_template_from_payload(db, "Empty", [])
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_add_template_from_payload_rejects_missing_title(db):
    with pytest.raises(HTTPException) as exc:
        await crud.add_template_from_payload(db, "   ", [{"type": 1, "title": "X", "image": "x", "platform": "linux"}])
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_add_template_from_payload_rejects_duplicate_title(db):
    p = [{"type": 1, "title": "X", "image": "x", "platform": "linux"}]
    await crud.add_template_from_payload(db, "Dup", p)
    with pytest.raises(HTTPException) as exc:
        await crud.add_template_from_payload(db, "Dup", p)
    assert exc.value.status_code == 409


# --- crud.replace_template_items -------------------------------------------

@pytest.mark.asyncio
async def test_replace_template_items_wipes_and_rebuilds(db):
    p1 = [{"type": 1, "title": "A", "image": "a", "platform": "linux"}]
    p2 = [
        {"type": 1, "title": "B1", "image": "b1", "platform": "linux"},
        {"type": 1, "title": "B2", "image": "b2", "platform": "linux"},
    ]
    t = await crud.add_template_from_payload(db, "T", p1)
    await crud.replace_template_items(db, t.id, p2)
    result = await db.execute(
        select(TemplateItem).filter(TemplateItem.template_id == t.id)
    )
    items = result.scalars().all()
    titles = sorted(i.title for i in items)
    assert titles == ["B1", "B2"]


@pytest.mark.asyncio
async def test_replace_template_items_404_on_missing(db):
    with pytest.raises(HTTPException) as exc:
        await crud.replace_template_items(db, 99999, [{"type": 1, "title": "X", "image": "x", "platform": "linux"}])
    assert exc.value.status_code == 404


# --- /refresh rejects local:// templates -----------------------------------

@pytest.mark.asyncio
async def test_refresh_template_rejects_local_url(db):
    p = [{"type": 1, "title": "X", "image": "x", "platform": "linux"}]
    t = await crud.add_template_from_payload(db, "LocalOnly", p)
    with pytest.raises(HTTPException) as exc:
        await crud.refresh_template(db, t.id)
    # 400 ("no remote source"), NOT 500 from validate_url's scheme barf.
    assert exc.value.status_code == 400
    assert "remote source" in exc.value.detail


# --- /api/templates/upload -------------------------------------------------

def _upload(data: bytes, content_type: str = "application/json") -> UploadFile:
    up = MagicMock(spec=UploadFile)
    up.content_type = content_type
    up.file = io.BytesIO(data)
    return up


@pytest.mark.asyncio
async def test_upload_template_happy_path(db):
    await _add_superuser(db)
    payload = json.dumps([
        {"type": 1, "title": "Plex", "image": "plexinc/pms-docker", "platform": "linux"}
    ]).encode("utf-8")
    t = await upload_template(
        title="Media", upload=_upload(payload), db=db, Authorize=MockAuth()
    )
    assert t.title == "Media"
    assert t.url.startswith("local://")


@pytest.mark.asyncio
async def test_upload_template_rejects_oversize(db):
    await _add_superuser(db)
    big = b"[" + (b'{"type":1,"title":"X","image":"x","platform":"linux"},') * 100000 + b"{}]"
    with pytest.raises(HTTPException) as exc:
        await upload_template(title="Big", upload=_upload(big), db=db, Authorize=MockAuth())
    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_upload_template_rejects_non_json_content_type(db):
    await _add_superuser(db)
    with pytest.raises(HTTPException) as exc:
        await upload_template(
            title="X", upload=_upload(b"[]", content_type="application/zip"),
            db=db, Authorize=MockAuth(),
        )
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_upload_template_rejects_malformed_json(db):
    await _add_superuser(db)
    with pytest.raises(HTTPException) as exc:
        await upload_template(
            title="X", upload=_upload(b"not json at all"),
            db=db, Authorize=MockAuth(),
        )
    assert exc.value.status_code == 400


# --- /api/templates/manual + edit ------------------------------------------

@pytest.mark.asyncio
async def test_create_manual_template(db):
    await _add_superuser(db)
    body = ManualTemplateBody(
        title="Hand-rolled",
        content=[{"type": 1, "title": "X", "image": "x", "platform": "linux"}],
    )
    t = await create_manual_template(body=body, db=db, Authorize=MockAuth())
    assert t.url.startswith("local://")


@pytest.mark.asyncio
async def test_edit_template_content(db):
    await _add_superuser(db)
    body = ManualTemplateBody(
        title="E",
        content=[{"type": 1, "title": "old", "image": "x", "platform": "linux"}],
    )
    t = await create_manual_template(body=body, db=db, Authorize=MockAuth())
    edit_body = EditTemplateBody(
        title="E2",
        content=[{"type": 1, "title": "new", "image": "y", "platform": "linux"}],
    )
    edited = await edit_template_content(id=t.id, body=edit_body, db=db, Authorize=MockAuth())
    assert edited.title == "E2"
    result = await db.execute(
        select(TemplateItem).filter(TemplateItem.template_id == t.id)
    )
    items = result.scalars().all()
    assert [i.title for i in items] == ["new"]


# --- bundled-catalog seeding ----------------------------------------------

@pytest.mark.asyncio
async def test_seed_bundled_catalogs_imports_each_json(db, tmp_path, monkeypatch):
    """*.json in BUILTIN_CATALOG_DIR -> one catalog row per file, titled
    from the filename stem."""
    p1 = tmp_path / "yacht.json"
    p1.write_text(json.dumps([
        {"type": 1, "title": "A", "image": "a", "platform": "linux"}
    ]))
    p2 = tmp_path / "extras.json"
    p2.write_text(json.dumps([
        {"type": 1, "title": "B", "image": "b", "platform": "linux"}
    ]))
    # Not JSON — must be skipped without erroring.
    (tmp_path / "readme.txt").write_text("ignore me")

    monkeypatch.setattr(
        "api.settings.get_settings",
        lambda: type("S", (), {
            "BUILTIN_CATALOG_DIR": str(tmp_path),
            "DEFAULT_TEMPLATE_URLS": "",
        })(),
    )
    await crud._seed_bundled_catalogs(db)

    result = await db.execute(select(Template))
    titles = sorted(t.title for t in result.scalars().all())
    assert titles == ["extras", "yacht"]


@pytest.mark.asyncio
async def test_seed_bundled_catalogs_idempotent(db, tmp_path, monkeypatch):
    (tmp_path / "yacht.json").write_text(json.dumps([
        {"type": 1, "title": "A", "image": "a", "platform": "linux"}
    ]))
    monkeypatch.setattr(
        "api.settings.get_settings",
        lambda: type("S", (), {
            "BUILTIN_CATALOG_DIR": str(tmp_path),
            "DEFAULT_TEMPLATE_URLS": "",
        })(),
    )
    await crud._seed_bundled_catalogs(db)
    await crud._seed_bundled_catalogs(db)
    assert await _count(db, Template) == 1


@pytest.mark.asyncio
async def test_seed_bundled_catalogs_tolerates_corrupt_file(db, tmp_path, monkeypatch, caplog):
    (tmp_path / "broken.json").write_text("{not json")
    (tmp_path / "good.json").write_text(json.dumps([
        {"type": 1, "title": "X", "image": "x", "platform": "linux"}
    ]))
    monkeypatch.setattr(
        "api.settings.get_settings",
        lambda: type("S", (), {
            "BUILTIN_CATALOG_DIR": str(tmp_path),
            "DEFAULT_TEMPLATE_URLS": "",
        })(),
    )
    with caplog.at_level("ERROR"):
        await crud._seed_bundled_catalogs(db)
    # Good catalog still landed; broken one logged but didn't crash.
    result = await db.execute(select(Template).filter(Template.title == "good"))
    assert len(result.scalars().all()) == 1
    assert any("broken" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_seed_bundled_catalogs_missing_dir_is_noop(db, monkeypatch):
    monkeypatch.setattr(
        "api.settings.get_settings",
        lambda: type("S", (), {
            "BUILTIN_CATALOG_DIR": "/nonexistent/path/abc",
            "DEFAULT_TEMPLATE_URLS": "",
        })(),
    )
    await crud._seed_bundled_catalogs(db)  # must not raise
    assert await _count(db, Template) == 0


@pytest.mark.asyncio
async def test_seed_bundled_catalogs_handles_settings_without_field(db, monkeypatch, tmp_path):
    """Defensive against test stubs that don't declare BUILTIN_CATALOG_DIR."""
    monkeypatch.setattr(
        "api.settings.get_settings",
        lambda: type("S", (), {})(),  # no BUILTIN_CATALOG_DIR at all
    )
    await crud._seed_bundled_catalogs(db)  # must not raise
