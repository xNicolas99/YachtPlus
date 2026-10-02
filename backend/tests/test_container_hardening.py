"""Security defaults, explicit compatibility and normalized mount paths."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from fastapi import HTTPException

from api.utils.container_security import workload_options, secure_compose_content
from api.db.schemas.apps import DeployForm, VolumesSchema
from api.utils.apps import conv_volumes2data


def test_restricted_options_are_explicit():
    options = workload_options()
    assert options["user"] == "1000:1000"
    assert options["read_only"] is True
    assert options["cap_drop"] == ["ALL"]
    assert options["security_opt"] == ["no-new-privileges:true"]
    assert options["pids_limit"] == 256
    assert set(options["tmpfs"]) == {"/tmp", "/run"}


@pytest.mark.parametrize("user", ["root", "0", "0:1000", "1000:0", "-1", "65534:root", "1000;id", "2147483648", "", None])
def test_restricted_never_accepts_root_or_invalid_user(user):
    with pytest.raises(HTTPException) as error:
        workload_options(user=user)
    assert error.value.status_code == 422


def test_compatibility_is_explicit_and_still_limits_privilege():
    with pytest.raises(HTTPException):
        workload_options("image-default")
    options = workload_options("image-default", confirmed=True)
    assert "user" not in options
    assert options["security_opt"] == ["no-new-privileges:true"]
    assert options["pids_limit"] == 256


def test_launch_passes_profile_to_daemon_before_any_existing_container_removal(monkeypatch):
    from api.actions.apps import _launch_app_sync
    from api.utils import docker_client
    client = MagicMock()
    monkeypatch.setattr(docker_client, "get_sync_docker_client", lambda: client)
    args = ("web", "nginx", {}, None, {}, {}, None, "bridge", {}, [], [], {}, {}, [], None, None, False, None)
    _launch_app_sync(*args)
    assert client.containers.run.call_args.kwargs["read_only"] is True
    assert client.containers.run.call_args.kwargs["user"] == "1000:1000"
    assert client.containers.run.call_args.kwargs["cap_drop"] == ["ALL"]
    client.reset_mock()
    invalid = list(args)
    invalid[-2] = True
    with pytest.raises(HTTPException):
        _launch_app_sync(*invalid, container_user="0")
    client.containers.get.assert_not_called()
    client.containers.run.assert_not_called()


@pytest.mark.asyncio
async def test_non_admin_cannot_deploy_compatibility(monkeypatch):
    from api.routers import apps
    monkeypatch.setattr(apps, "auth_check", AsyncMock())
    monkeypatch.setattr(apps, "check_permission", AsyncMock())
    monkeypatch.setattr(apps.users_crud, "get_user_by_name", AsyncMock(return_value=SimpleNamespace(is_superuser=False)))
    deploy = AsyncMock()
    monkeypatch.setattr(apps.actions, "deploy_app", deploy)
    authorization = SimpleNamespace(get_jwt_subject=AsyncMock(return_value="operator"))
    with pytest.raises(HTTPException) as error:
        await apps.deploy_app(DeployForm(name="web", image="nginx", security_profile="image-default", confirm_image_default=True), authorization, MagicMock())
    assert error.value.status_code == 403
    deploy.assert_not_called()


@pytest.mark.parametrize("bind", ["/config/../etc", "/config/../../root", "/config/sub/../../../proc", "/config/../run/docker.sock"])
def test_mount_whitelist_cannot_be_escaped(bind, monkeypatch):
    monkeypatch.setenv("VOLUME_WHITELIST", "/config")
    with pytest.raises(HTTPException):
        conv_volumes2data([VolumesSchema(container="/data", bind=bind)], [])


def test_mount_variables_are_validated_after_substitution(monkeypatch):
    monkeypatch.setenv("VOLUME_WHITELIST", "/config")
    with pytest.raises(HTTPException):
        conv_volumes2data([VolumesSchema(container="/data", bind="!DATA!")], [SimpleNamespace(variable="!DATA!", replacement="/config/../../etc")])


def test_compose_defaults_are_visible_and_preserve_application_options():
    content = "services:\n  web:\n    image: nginx\n    environment:\n      TZ: UTC\n    volumes:\n      - data:/data\nvolumes:\n  data: {}\n"
    document = yaml.safe_load(secure_compose_content(content))
    service = document["services"]["web"]
    assert service["user"] == "1000:1000"
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]
    assert service["environment"] == {"TZ": "UTC"}
    assert service["volumes"] == ["data:/data"]
    assert secure_compose_content(secure_compose_content(content)) == secure_compose_content(content)


@pytest.mark.parametrize("option", [
    "user: '0'", "read_only: false", "privileged: true", "network_mode: host",
    "network_mode: '${NETWORK}'", "pid: host", "ipc: host", "devices: [/dev/sda]",
    "cap_add: [SYS_ADMIN]", "security_opt: [seccomp:unconfined]", "volumes: ['/etc:/host']",
    "volumes: ['/config/../../run/docker.sock:/var/run/docker.sock']", "volumes: ['${HOST_PATH}:/data']",
    "volumes: ['../../../etc:/host']", "volumes: ['./../../../etc:/host']",
    "volumes: ['/dev:/dev']", "volumes: ['//etc:/host']",
])
def test_compose_restricted_rejects_elevated_or_opaque_options(option):
    with pytest.raises(HTTPException) as error:
        secure_compose_content(f"services:\n  web:\n    image: nginx\n    {option}\n")
    assert error.value.status_code == 422


def test_compose_compatibility_preserves_explicit_image_user():
    document = yaml.safe_load(secure_compose_content("services:\n  database:\n    image: postgres\n    user: '0'\n    x-yachtplus-security: image-default\n"))
    service = document["services"]["database"]
    assert service["user"] == "0"
    assert service["security_opt"] == ["no-new-privileges:true"]
    assert service["pids_limit"] == 256


def test_compose_named_volume_cannot_hide_sensitive_host_bind():
    content = "services:\n  web:\n    image: nginx\n    volumes: [hostetc:/host]\nvolumes:\n  hostetc:\n    driver_opts:\n      type: none\n      o: bind\n      device: /etc\n"
    with pytest.raises(HTTPException, match="driver"):
        secure_compose_content(content)


@pytest.mark.asyncio
async def test_raw_compose_edit_requires_active_admin_before_write(monkeypatch):
    from api.routers import compose
    from api.db.schemas.compose import ComposeWrite
    monkeypatch.setattr(compose, "auth_check", AsyncMock())
    monkeypatch.setattr(compose, "require_superuser", AsyncMock(side_effect=HTTPException(403, "Admin required")))
    write = AsyncMock()
    monkeypatch.setattr(compose, "write_compose", write)
    with pytest.raises(HTTPException) as error:
        await compose.write_compose_project(MagicMock(), "web", ComposeWrite(name="web", content="services: {}"), MagicMock(), MagicMock())
    assert error.value.status_code == 403
    write.assert_not_called()
