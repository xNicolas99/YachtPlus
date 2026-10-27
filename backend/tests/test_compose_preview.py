"""Compose previews are read-only and bind confirmation to the actual saved file."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.actions import compose as actions
from api.db.schemas.compose import ComposeWrite
from api.routers import compose as router


CONTENT = "services:\n  web:\n    image: nginx:stable\n"


@pytest.fixture
def project_root(tmp_path, monkeypatch):
    monkeypatch.setattr(actions, "get_settings", lambda: SimpleNamespace(COMPOSE_DIR=str(tmp_path)))
    return tmp_path


def test_preview_new_project_creates_no_files_or_directories(project_root):
    form = ComposeWrite(name="example", content=CONTENT)
    preview = actions._preview_compose_sync(form)
    assert list(project_root.iterdir()) == []
    assert preview["affected_services"] == [{"name": "web", "change": "added"}]
    assert "user: 1000:1000" in preview["normalized_content"]
    assert "read_only: true" in preview["normalized_content"]
    assert "read_only" in preview["security_changes"][0]["fields"]
    assert "+    read_only: true" in preview["diff"]
    assert len(preview["preview_token"]) == 64


def test_preview_of_missing_compose_root_does_not_create_it(tmp_path, monkeypatch):
    directory = tmp_path / "missing-root"
    monkeypatch.setattr(actions, "get_settings", lambda: SimpleNamespace(COMPOSE_DIR=str(directory)))
    actions._preview_compose_sync(ComposeWrite(name="example", content=CONTENT))
    assert not directory.exists()


def test_confirmed_preview_and_actual_file_are_identical(project_root):
    form = ComposeWrite(name="example", content=CONTENT)
    preview = actions._preview_compose_sync(form)
    saved = actions._write_compose_sync(form.model_copy(update={"preview_token": preview["preview_token"]}))
    assert saved["content"] == preview["normalized_content"]
    assert (project_root / "example/docker-compose.yml").read_text() == preview["normalized_content"]


def test_preview_reports_changed_and_removed_services_and_preserves_filename(project_root):
    directory = project_root / "example"
    directory.mkdir()
    original = "services:\n  old:\n    image: busybox\n  web:\n    image: nginx:old\n"
    destination = directory / "compose.yaml"
    destination.write_text(original)
    form = ComposeWrite(name="example", content=CONTENT)
    preview = actions._preview_compose_sync(form)
    assert destination.read_text() == original
    assert preview["affected_services"] == [{"name": "old", "change": "removed"}, {"name": "web", "change": "changed"}]
    assert "-    image: nginx:old" in preview["diff"]
    actions._write_compose_sync(form.model_copy(update={"preview_token": preview["preview_token"]}))
    assert destination.read_text() == preview["normalized_content"]
    assert not (directory / "docker-compose.yml").exists()


def test_changed_source_file_requires_a_new_preview(project_root):
    form = ComposeWrite(name="example", content=CONTENT)
    actions._write_compose_sync(form)
    preview = actions._preview_compose_sync(form)
    destination = project_root / "example/docker-compose.yml"
    altered = "services:\n  externally_added:\n    image: busybox\n"
    destination.write_text(altered)
    with pytest.raises(HTTPException) as error:
        actions._write_compose_sync(form.model_copy(update={"preview_token": preview["preview_token"]}))
    assert error.value.status_code == 409
    assert destination.read_text() == altered


def test_changed_input_cannot_reuse_a_preview_token(project_root):
    form = ComposeWrite(name="example", content=CONTENT)
    preview = actions._preview_compose_sync(form)
    changed = form.model_copy(update={"content": CONTENT.replace("stable", "new"), "preview_token": preview["preview_token"]})
    with pytest.raises(HTTPException) as error:
        actions._write_compose_sync(changed)
    assert error.value.status_code == 409
    assert list(project_root.iterdir()) == []


def test_invalid_existing_yaml_can_be_repaired_with_explicit_warning(project_root):
    directory = project_root / "example"
    directory.mkdir()
    destination = directory / "docker-compose.yml"
    destination.write_text("services: [invalid")
    form = ComposeWrite(name="example", content=CONTENT)
    preview = actions._preview_compose_sync(form)
    assert "invalid YAML" in preview["warnings"][0]
    assert destination.read_text() == "services: [invalid"
    actions._write_compose_sync(form.model_copy(update={"preview_token": preview["preview_token"]}))
    assert destination.read_text() == preview["normalized_content"]


def test_normalized_configuration_produces_no_security_changes(project_root):
    initial = ComposeWrite(name="example", content=CONTENT)
    saved = actions._write_compose_sync(initial)
    preview = actions._preview_compose_sync(ComposeWrite(name="example", content=saved["content"]))
    assert preview["security_changes"] == []
    assert preview["affected_services"] == []
    assert preview["diff"] == ""


def test_preview_rejects_project_symlinks_without_changing_target(project_root):
    target = project_root / "target"
    target.mkdir()
    destination = target / "compose.yml"
    destination.write_text(CONTENT)
    try:
        (project_root / "example").symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are unavailable")
    with pytest.raises(HTTPException) as error:
        actions._preview_compose_sync(ComposeWrite(name="example", content=CONTENT))
    assert error.value.status_code == 400
    assert destination.read_text() == CONTENT
    assert list(target.iterdir()) == [destination]


@pytest.mark.parametrize("content,status", [
    ("", 422), ("services: [", 422), ("services: {}", 422),
    ("services:\n  web:\n    image: nginx\n    privileged: true\n", 422),
    ("a" * (actions._COMPOSE_MAX_BYTES + 1), 413),
])
def test_preview_uses_write_validation_without_filesystem_changes(project_root, content, status):
    with pytest.raises(HTTPException) as error:
        actions._preview_compose_sync(ComposeWrite(name="example", content=content))
    assert error.value.status_code == status
    assert list(project_root.iterdir()) == []


@pytest.mark.asyncio
async def test_preview_rejects_api_keys_before_reading_configuration(monkeypatch):
    monkeypatch.setattr(router, "auth_check", AsyncMock())
    admin = AsyncMock()
    preview = AsyncMock()
    monkeypatch.setattr(router, "require_superuser", admin)
    monkeypatch.setattr(router, "preview_compose", preview)
    authorization = SimpleNamespace(is_api_key=lambda: True)
    with pytest.raises(HTTPException) as error:
        await router.preview_compose_project(MagicMock(), ComposeWrite(name="example", content=CONTENT), authorization, MagicMock())
    assert error.value.status_code == 403
    admin.assert_not_awaited()
    preview.assert_not_awaited()


@pytest.mark.asyncio
async def test_preview_requires_active_administrator_before_reading_configuration(monkeypatch):
    monkeypatch.setattr(router, "auth_check", AsyncMock())
    monkeypatch.setattr(router, "require_superuser", AsyncMock(side_effect=HTTPException(403, "Active administrator required")))
    preview = AsyncMock()
    monkeypatch.setattr(router, "preview_compose", preview)
    authorization = SimpleNamespace(is_api_key=lambda: False)
    with pytest.raises(HTTPException) as error:
        await router.preview_compose_project(MagicMock(), ComposeWrite(name="example", content=CONTENT), authorization, MagicMock())
    assert error.value.status_code == 403
    preview.assert_not_awaited()


def test_concurrent_save_is_rejected_before_writing(project_root):
    form = ComposeWrite(name="example", content=CONTENT)
    with actions._compose_save_lock(form.name):
        with pytest.raises(HTTPException) as error:
            actions._write_compose_sync(form)
    assert error.value.status_code == 409
    assert list(project_root.iterdir()) == []


def test_shared_network_changes_include_dependent_services(project_root):
    content = CONTENT + "    networks: [frontend]\nnetworks:\n  frontend:\n    internal: false\n"
    original = actions._write_compose_sync(ComposeWrite(name="example", content=content))
    changed = original["content"].replace("internal: false", "internal: true")
    preview = actions._preview_compose_sync(ComposeWrite(name="example", content=changed))
    assert preview["affected_services"] == [{"name": "web", "change": "changed"}]
    assert preview["security_changes"] == []
