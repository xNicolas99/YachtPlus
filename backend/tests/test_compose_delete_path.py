"""Regression tests for the compose delete path construction."""
import os
import pathlib
import pytest
import tempfile

from fastapi import HTTPException
from api.actions.compose import _delete_compose_sync


def test_delete_compose_resolves_inside_compose_dir():
    """Deleting a project must resolve inside the configured compose dir."""
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = pathlib.Path(tmp) / "demo"
        project_dir.mkdir()
        (project_dir / "docker-compose.yml").write_text("services:\n  web:\n    image: nginx\n")

        with pytest.MonkeyPatch().context() as ctx:
            ctx.setenv("COMPOSE_DIR", tmp + os.sep)
            from api.settings import get_settings

            get_settings.cache_clear()

            _delete_compose_sync("demo")
            assert not project_dir.exists()


def test_delete_compose_rejects_traversal_project_name():
    """Project names with path traversal must be rejected before touching disk."""
    with tempfile.TemporaryDirectory() as tmp:
        outside = pathlib.Path(tmp) / "outside"
        outside.mkdir()
        (outside / "docker-compose.yml").write_text("services:\n  web:\n    image: nginx\n")

        with pytest.MonkeyPatch().context() as ctx:
            # Place the compose dir so that a traversal name would otherwise hit `outside`.
            compose_dir = pathlib.Path(tmp) / "compose"
            compose_dir.mkdir()
            ctx.setenv("COMPOSE_DIR", str(compose_dir) + os.sep)
            from api.settings import get_settings

            get_settings.cache_clear()

            with pytest.raises(HTTPException) as exc:
                _delete_compose_sync("../outside")
            assert exc.value.status_code == 400


def test_delete_compose_rejects_missing_directory():
    """Deleting a non-existent project must return 404."""
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.MonkeyPatch().context() as ctx:
            ctx.setenv("COMPOSE_DIR", str(pathlib.Path(tmp) / "compose") + os.sep)
            from api.settings import get_settings

            get_settings.cache_clear()

            with pytest.raises(HTTPException) as exc:
                _delete_compose_sync("ghost")
            assert exc.value.status_code == 404
