"""Regression for BUG-004: support-bundle generation crashed on empty YAML.

`yaml.load` returns None for an empty file. The bundle generator called
`.get("services", {})` on that None and raised AttributeError, taking down
the support endpoint instead of just emitting an empty zip.
"""
import io
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from api.actions import compose as actions_compose


@pytest.fixture
def empty_compose_file(tmp_path, monkeypatch):
    compose_dir = tmp_path / "demo"
    compose_dir.mkdir()
    compose_file = compose_dir / "docker-compose.yml"
    compose_file.write_text("")  # empty -> yaml.load returns None
    # COMPOSE_DIR isn't a declared Pydantic field on Settings (extra='forbid'),
    # so monkeypatch.setattr won't accept it. Bypass via object.__setattr__.
    object.__setattr__(actions_compose.settings, "COMPOSE_DIR", str(tmp_path) + os.sep)
    return compose_file


def test_support_bundle_empty_yaml_does_not_crash(empty_compose_file, monkeypatch):
    # find_yml_files maps project name -> abs file path. Stub it to point at
    # the test fixture rather than walking COMPOSE_DIR which depends on cwd.
    monkeypatch.setattr(
        actions_compose,
        "find_yml_files",
        lambda _path: {"demo": str(empty_compose_file)},
    )

    fake_dclient = MagicMock()
    fake_dclient.containers.get.side_effect = Exception("no container")
    with patch(
        "api.utils.docker_client.get_sync_docker_client",
        return_value=fake_dclient,
    ):
        result = actions_compose._generate_support_bundle_sync("demo")

    # Empty compose -> empty (or minimal) zip, but crucially no exception.
    assert isinstance(result, io.BytesIO)


def test_support_bundle_yaml_without_services_key(tmp_path, monkeypatch):
    compose_dir = tmp_path / "demo"
    compose_dir.mkdir()
    compose_file = compose_dir / "docker-compose.yml"
    compose_file.write_text("version: '3.9'\n")  # valid YAML, no services
    # COMPOSE_DIR isn't a declared Pydantic field on Settings (extra='forbid'),
    # so monkeypatch.setattr won't accept it. Bypass via object.__setattr__.
    object.__setattr__(actions_compose.settings, "COMPOSE_DIR", str(tmp_path) + os.sep)
    monkeypatch.setattr(
        actions_compose,
        "find_yml_files",
        lambda _path: {"demo": str(compose_file)},
    )

    fake_dclient = MagicMock()
    fake_dclient.containers.get.side_effect = Exception("no container")
    with patch(
        "api.utils.docker_client.get_sync_docker_client",
        return_value=fake_dclient,
    ):
        result = actions_compose._generate_support_bundle_sync("demo")

    assert isinstance(result, io.BytesIO)
