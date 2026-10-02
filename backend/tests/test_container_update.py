"""Real update transaction orchestration with a simulated Docker daemon."""
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace

import pytest
import aiodocker
from fastapi import HTTPException

from api.utils import container_update as update


def attributes():
    return {
        "Id": "a" * 64, "Image": "sha256:old", "Name": "/web",
        "Config": {"Image": "nginx:stable", "Hostname": "a" * 12, "User": "1000:1000", "Env": ["TZ=UTC"], "Volumes": {"/data": {}}},
        "HostConfig": {"Binds": None, "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"], "ReadonlyRootfs": True},
        "State": {"Running": True},
        "Mounts": [{"Type": "volume", "Name": "anonymous-existing", "Destination": "/data", "RW": True}],
        "NetworkSettings": {"Networks": {"private": {"Aliases": ["web", "a" * 12], "IPAddress": "172.20.0.2", "IPAMConfig": {"IPv4Address": "172.20.0.2"}}}},
    }


def daemon():
    client = MagicMock()
    old = MagicMock(id="a" * 64, attrs=attributes())
    new = MagicMock(attrs={"State": {"Running": True}})
    client.containers.get.side_effect = [old, new]
    client.images.pull.return_value.id = "sha256:new"
    client.api.create_container_from_config.return_value = {"Id": "new"}
    return client, old, new


@pytest.mark.parametrize("endpoint", [None, "unix:///var/run/docker.sock", "tcp://u:p@proxy:2375", "tcp://proxy:bad", "tcp://proxy:2375/path", "tcp://proxy:2375?token=secret"])
def test_no_socket_fallback_or_ambiguous_endpoint(endpoint):
    with pytest.raises(ValueError):
        update.proxy_endpoint(endpoint)


def test_replacement_preserves_volumes_security_and_static_networks():
    original = attributes()
    snapshot = deepcopy(original)
    config = update.replacement_config(original)
    assert config["User"] == "1000:1000"
    assert config["HostConfig"]["ReadonlyRootfs"] is True
    assert config["HostConfig"]["CapDrop"] == ["ALL"]
    assert config["HostConfig"]["Binds"] == ["anonymous-existing:/data:rw"]
    assert config["NetworkingConfig"]["EndpointsConfig"]["private"] == {"Aliases": ["web"], "IPAMConfig": {"IPv4Address": "172.20.0.2"}}
    assert original == snapshot
    assert "Hostname" not in config


def test_explicit_hostname_is_preserved():
    original = attributes()
    original["Config"]["Hostname"] = "database"
    assert update.replacement_config(original)["Hostname"] == "database"


def test_unchanged_image_does_not_stop_or_recreate():
    client, old, new = daemon()
    client.images.pull.return_value.id = "sha256:old"
    assert update.update_container(client, "web") == {"updated": False}
    old.stop.assert_not_called()
    client.api.create_container_from_config.assert_not_called()


def test_success_pins_pulled_image_and_removes_old_without_volumes(monkeypatch):
    client, old, new = daemon()
    monkeypatch.setattr(update, "_wait_started", MagicMock())
    assert update.update_container(client, "web") == {"updated": True}
    config = client.api.create_container_from_config.call_args.args[0]
    assert config["Image"] == "sha256:new"
    assert config["Labels"][update.UPDATE_IMAGE_LABEL] == "nginx:stable"
    client.networks.get.return_value.disconnect.assert_called_once_with(old)
    old.stop.assert_called_once_with(timeout=30)
    new.start.assert_called_once()
    old.remove.assert_called_once_with(v=False)


@pytest.mark.parametrize("failure", ["pull", "create", "start", "health"])
def test_failed_update_keeps_original_and_rolls_back_networks(failure, monkeypatch):
    client, old, new = daemon()
    if failure == "pull":
        client.images.pull.side_effect = RuntimeError("pull failed")
    elif failure == "create":
        client.api.create_container_from_config.side_effect = RuntimeError("create failed")
    elif failure == "start":
        new.start.side_effect = RuntimeError("start failed")
    else:
        monkeypatch.setattr(update, "_wait_started", MagicMock(side_effect=RuntimeError("unhealthy")))
    with pytest.raises(RuntimeError):
        update.update_container(client, "web")
    old.remove.assert_not_called()
    if failure == "pull":
        old.stop.assert_not_called()
    else:
        assert old.rename.call_args.args == ("web",)
        old.start.assert_called_once()
        client.networks.get.return_value.connect.assert_called_once_with(old, aliases=["web"], ipv4_address="172.20.0.2")
    if failure in ("start", "health"):
        new.remove.assert_called_once_with(force=True, v=False)


def test_stopped_container_remains_stopped_after_update():
    client, old, new = daemon()
    old.attrs["State"]["Running"] = False
    update.update_container(client, "web")
    old.stop.assert_not_called()
    new.start.assert_not_called()


@pytest.mark.parametrize("broken", ["replacement cleanup", "network reconnect"])
def test_rollback_attempts_remaining_steps_after_secondary_failure(broken, monkeypatch):
    client, old, new = daemon()
    monkeypatch.setattr(update, "_wait_started", MagicMock(side_effect=RuntimeError("unhealthy")))
    if broken == "replacement cleanup":
        new.remove.side_effect = RuntimeError("remove failed")
    else:
        client.networks.get.return_value.connect.side_effect = RuntimeError("connect failed")
    with pytest.raises(RuntimeError, match="rollback reported errors"):
        update.update_container(client, "web")
    old.rename.assert_called_with("web")
    old.start.assert_called_once()
    client.networks.get.return_value.connect.assert_called_once()
    old.remove.assert_not_called()


def test_auto_remove_rejected_before_pull_or_stop():
    client, old, new = daemon()
    old.attrs["HostConfig"]["AutoRemove"] = True
    with pytest.raises(ValueError):
        update.update_container(client, "web")
    client.images.pull.assert_not_called()
    old.stop.assert_not_called()


def test_subsequent_updates_use_original_registry_reference(monkeypatch):
    client, old, new = daemon()
    old.attrs["Config"]["Image"] = "sha256:old"
    old.attrs["Config"]["Labels"] = {update.UPDATE_IMAGE_LABEL: "nginx:stable"}
    monkeypatch.setattr(update, "_wait_started", MagicMock())
    update.update_container(client, "web")
    client.images.pull.assert_called_once_with("nginx:stable")
    assert update.update_image_reference(client.api.create_container_from_config.call_args.args[0]) == "nginx:stable"


def test_long_anonymous_volume_uses_inspected_existing_name():
    original = attributes()
    original["HostConfig"]["Mounts"] = [{"Type": "volume", "Source": "", "Target": "/data", "ReadOnly": False}]
    config = update.replacement_config(original)
    assert config["HostConfig"]["Mounts"][0]["Source"] == "anonymous-existing"
    assert config["HostConfig"]["Binds"] == []


def test_long_named_volume_is_preserved_without_duplicate_bind():
    original = attributes()
    original["HostConfig"]["Mounts"] = [{"Type": "volume", "Source": "named-data", "Target": "/data"}]
    config = update.replacement_config(original)
    assert config["HostConfig"]["Mounts"][0]["Source"] == "named-data"
    assert config["HostConfig"]["Binds"] == []


def test_backup_cleanup_failure_does_not_misreport_successful_update(monkeypatch):
    client, old, new = daemon()
    monkeypatch.setattr(update, "_wait_started", MagicMock())
    old.remove.side_effect = RuntimeError("cleanup failed")
    result = update.update_container(client, "web")
    assert result["updated"] is True
    assert result["retained_original"].startswith("web_rollback_")
    old.start.assert_not_called()


@pytest.mark.asyncio
async def test_update_worker_is_nonroot_and_never_mounts_socket(monkeypatch):
    from api.actions import apps
    monkeypatch.setattr(apps, "get_settings", lambda: SimpleNamespace(DOCKER_HOST="tcp://dockerproxy:2375"))
    monkeypatch.setattr(apps, "_get_self_id", AsyncMock(return_value="self"))
    monkeypatch.setenv("YACHT_DOCKER_PROXY_NETWORK", "yacht_docker_api")
    own = SimpleNamespace(show=AsyncMock(return_value={"Image": "sha256:yacht", "NetworkSettings": {"Networks": {"yacht_docker_api": {}}}}))
    worker = SimpleNamespace(start=AsyncMock(), delete=AsyncMock())
    target = SimpleNamespace(show=AsyncMock(return_value=attributes()))
    client = SimpleNamespace(containers=SimpleNamespace(get=AsyncMock(side_effect=[target, own, aiodocker.exceptions.DockerError(404, "not found")]), create=AsyncMock(return_value=worker)), networks=SimpleNamespace(get=AsyncMock()))
    await apps._start_update_worker(client, "web")
    config = client.containers.create.call_args.kwargs["config"]
    assert config["User"] == "1000:1000"
    assert config["HostConfig"]["CapDrop"] == ["ALL"]
    assert config["HostConfig"]["ReadonlyRootfs"] is True
    assert config["HostConfig"]["NetworkMode"] == "yacht_docker_api"
    assert "Binds" not in config["HostConfig"]
    assert "tcp://dockerproxy:2375" in config["Env"][0]
    assert "watchtower" not in str(config).lower()


@pytest.mark.asyncio
async def test_worker_refuses_socket_endpoint_before_any_daemon_calls(monkeypatch):
    from api.actions import apps
    monkeypatch.setattr(apps, "get_settings", lambda: SimpleNamespace(DOCKER_HOST="unix:///var/run/docker.sock"))
    client = MagicMock()
    with pytest.raises(HTTPException) as error:
        await apps._start_update_worker(client, "web")
    assert error.value.status_code == 409
    client.containers.get.assert_not_called()


@pytest.mark.parametrize("identity", ["docker-proxy", "fail2ban", "alias", "address"])
def test_security_infrastructure_cannot_be_stopped_by_update(identity, monkeypatch):
    client, old, new = daemon()
    monkeypatch.setenv("DOCKER_HOST", "tcp://dockerproxy:2375")
    if identity in ("docker-proxy", "fail2ban"):
        old.attrs["Config"]["Labels"] = {"local.yachtplus.infrastructure": identity}
    elif identity == "alias":
        old.attrs["NetworkSettings"]["Networks"]["private"]["Aliases"].append("dockerproxy")
    else:
        monkeypatch.setenv("DOCKER_HOST", "tcp://172.20.0.2:2375")
    with pytest.raises(ValueError):
        update.update_container(client, "web")
    old.stop.assert_not_called()
    client.images.pull.assert_not_called()


def test_application_self_update_remains_allowed():
    original = attributes()
    original["Config"]["Labels"] = {"local.yachtplus.infrastructure": "application"}
    update.validate_update_target(original, "tcp://dockerproxy:2375")


@pytest.mark.asyncio
async def test_worker_rejects_protection_target_before_creation(monkeypatch):
    from api.actions import apps
    monkeypatch.setattr(apps, "get_settings", lambda: SimpleNamespace(DOCKER_HOST="tcp://dockerproxy:2375"))
    monkeypatch.setenv("YACHT_DOCKER_PROXY_NETWORK", "yacht_docker_api")
    original = attributes()
    original["Config"]["Labels"] = {"local.yachtplus.infrastructure": "fail2ban"}
    target = SimpleNamespace(show=AsyncMock(return_value=original))
    client = SimpleNamespace(containers=SimpleNamespace(get=AsyncMock(return_value=target), create=AsyncMock()))
    with pytest.raises(HTTPException) as error:
        await apps._start_update_worker(client, "guard")
    assert error.value.status_code == 409
    client.containers.create.assert_not_called()


def test_lost_create_response_removes_only_proven_transaction(monkeypatch):
    client, old, new = daemon()
    monkeypatch.setattr(update.uuid, "uuid4", lambda: SimpleNamespace(hex="transaction"))
    new.attrs["Config"] = {"Labels": {"local.yachtplus.update.transaction": "transaction"}}
    client.api.create_container_from_config.side_effect = RuntimeError("response lost")
    with pytest.raises(RuntimeError, match="response lost"):
        update.update_container(client, "web")
    new.remove.assert_called_once_with(force=True, v=False)
    old.rename.assert_called_with("web")
    old.start.assert_called_once()
    old.remove.assert_not_called()


def test_lost_response_never_deletes_unrelated_container():
    client, old, new = daemon()
    new.attrs["Config"] = {"Labels": {"local.yachtplus.update.transaction": "other"}}
    client.api.create_container_from_config.side_effect = RuntimeError("response lost")
    with pytest.raises(RuntimeError):
        update.update_container(client, "web")
    new.remove.assert_not_called()
    new.stop.assert_not_called()
