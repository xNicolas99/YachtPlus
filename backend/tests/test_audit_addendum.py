"""Integration regressions found during final audit review."""
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pyotp
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from api.actions import compose, containers
from api.db.crud import settings as settings_crud, templates
from api.db.models.containers import Template
from api.db.models.users import User


@pytest.mark.parametrize("key", ["volumes", "networks"])
def test_invalid_compose_resource_mapping_does_not_break_project_list(tmp_path, monkeypatch, key):
    project = tmp_path / "broken"
    project.mkdir()
    (project / "compose.yaml").write_text(f"services:\n  web:\n    image: nginx\n{key}: 1\n")
    monkeypatch.setattr(compose.get_settings(), "COMPOSE_DIR", str(tmp_path))
    assert compose._get_compose_projects_sync() == []


@pytest.mark.asyncio
async def test_invalid_settings_item_is_rejected_before_deleting_catalogs(db):
    original = Template(title="original", url="local://original")
    db.add(original)
    await db.commit()
    payload = {"templates": [{"title": "bad", "url": "local://bad", "items": [{"title": "incomplete"}]}], "variables": []}
    with pytest.raises(HTTPException) as error:
        await settings_crud.import_settings(db, SimpleNamespace(file=io.BytesIO(json.dumps(payload).encode())))
    assert error.value.status_code == 422
    assert (await db.execute(select(Template.title))).scalars().all() == ["original"]


@pytest.mark.asyncio
async def test_settings_import_ignores_external_ids_and_unknown_item_fields(db):
    payload = {"templates": [{"id": 9999, "title": "imported", "url": "local://imported", "items": [{"id": 8888, "type": 1, "title": "Web", "platform": "linux", "image": "nginx", "unknown": "ignored"}]}], "variables": []}
    await settings_crud.import_settings(db, SimpleNamespace(file=io.BytesIO(json.dumps(payload).encode())))
    saved = await templates.get_template(db, "local://imported")
    assert saved.id != 9999 and saved.items[0].id != 8888
    assert saved.items[0].image == "nginx"


@pytest.mark.asyncio
async def test_settings_import_commit_conflict_restores_original_catalogs(db):
    db.add(Template(title="original", url="local://original"))
    await db.commit()
    payload = {"templates": [{"title": "duplicate", "url": "local://first"}, {"title": "duplicate", "url": "local://second"}], "variables": []}
    with pytest.raises(HTTPException) as error:
        await settings_crud.import_settings(db, SimpleNamespace(file=io.BytesIO(json.dumps(payload).encode())))
    assert error.value.status_code == 422
    assert (await db.execute(select(Template.title))).scalars().all() == ["original"]


@pytest.mark.asyncio
async def test_dashboard_stats_accept_aiodocker_list_snapshot(monkeypatch):
    client = MagicMock()
    client.close = AsyncMock()
    container = SimpleNamespace(id="abc", _container={"Names": ["/web"]}, stats=AsyncMock(return_value=[{"memory_stats": {"usage": 4096, "limit": 8192, "stats": {"inactive_file": 1024}}}]))
    client.containers.list = AsyncMock(return_value=[container])
    monkeypatch.setattr(containers.aiodocker, "Docker", lambda **kwargs: client)
    monkeypatch.setattr(containers, "stats_cache", {})
    result = await containers.get_all_stats()
    assert result["web"]["memory_percent"] == 37.5
    client.close.assert_awaited_once()


def test_compose_save_updates_selected_filename_atomically(tmp_path, monkeypatch):
    project = tmp_path / "demo"
    project.mkdir()
    selected = project / "compose.yaml"
    selected.write_text("services:\n  web:\n    image: old\n")
    monkeypatch.setattr(compose.get_settings(), "COMPOSE_DIR", str(tmp_path))
    result = compose._write_compose_sync(SimpleNamespace(name="demo", content="services:\n  web:\n    image: nginx\n"))
    assert result["path"] == str(selected)
    assert "nginx" in selected.read_text()
    assert not (project / "docker-compose.yml").exists()


def test_compose_save_rejects_preferred_symlink(tmp_path, monkeypatch):
    project = tmp_path / "demo"
    project.mkdir()
    monkeypatch.setattr(compose.get_settings(), "COMPOSE_DIR", str(tmp_path))
    original = compose.pathlib.Path.is_symlink
    monkeypatch.setattr(compose.pathlib.Path, "is_symlink", lambda path: path.name == "compose.yaml" or original(path))
    with pytest.raises(HTTPException) as error:
        compose._write_compose_sync(SimpleNamespace(name="demo", content="services:\n  web:\n    image: nginx\n"))
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_totp_previous_window_cannot_be_replayed_in_next_window(db, monkeypatch):
    from api.utils import totp
    secret = pyotp.random_base32()
    user = User(username="clock", hashed_password="unused", otp_secret=secret, is_active=True)
    db.add(user)
    await db.commit()
    monkeypatch.setattr(totp, "decrypt", lambda value: value)
    now = 1800
    monkeypatch.setattr(totp.time, "time", lambda: now)
    code = pyotp.TOTP(secret).at(now - 30)
    assert await totp.consume_totp(db, user, code)
    await db.refresh(user)
    assert user.otp_last_step == 59
    assert not await totp.consume_totp(db, user, code)


@pytest.mark.asyncio
async def test_local_catalog_edit_does_not_lazy_load_in_async_session(db):
    saved = await templates.add_template_from_payload(db, "Local", [{"type": 1, "title": "First", "platform": "linux", "image": "nginx"}])
    identity = saved.id
    db.expire_all()
    edited = await templates.replace_template_items(db, identity, [{"type": 1, "title": "Second", "image": "alpine"}])
    assert [item.title for item in edited.items] == ["Second"]
