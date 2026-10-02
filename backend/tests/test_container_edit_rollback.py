"""Edited workloads retain recoverable configuration and volumes on failure."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import docker
from fastapi import HTTPException
import pytest

from api.actions.apps import _launch_app_sync
from api.actions import apps
from api.utils import container_edit, docker_client


def original_attributes():
    return {
        "Id": "a" * 64,
        "Name": "/original",
        "Image": "sha256:old",
        "Config": {
            "Image": "web:stable", "User": "1000:1000", "Volumes": {"/data": {}},
            "Healthcheck": {"Test": ["CMD", "check-health"], "Interval": 1000000000},
        },
        "HostConfig": {"Binds": None, "NetworkMode": "private", "ReadonlyRootfs": True},
        "Mounts": [{"Type": "volume", "Name": "existing-anonymous-data", "Destination": "/data", "RW": True}],
        "NetworkSettings": {"Networks": {
            "private": {"Aliases": ["original", "a" * 12], "IPAMConfig": {"IPv4Address": "172.20.0.5"}},
            "secondary": {"Aliases": ["secondary-alias"], "DriverOpts": {"foo": "bar"}},
        }},
        "State": {"Running": True},
    }


@pytest.fixture
def daemon(monkeypatch, tmp_path):
    client = MagicMock()
    old = MagicMock(id="a" * 64, attrs=original_attributes())
    new = MagicMock(id="b" * 64, attrs={"State": {"Running": True, "Health": {"Status": "healthy"}}})
    registry = {old.id: old, "original": old}
    networks = {name: MagicMock() for name in ("private", "secondary")}

    def lookup(identifier):
        if identifier not in registry:
            raise docker.errors.NotFound("not found")
        return registry[identifier]

    def rename(name):
        current = old.attrs["Name"].lstrip("/")
        if name in registry and registry[name].id != old.id:
            raise docker.errors.APIError("name conflict")
        registry.pop(current, None)
        registry[name] = old
        old.attrs["Name"] = "/" + name

    def create(**kwargs):
        if kwargs["name"] in registry:
            raise docker.errors.APIError("name conflict")
        new.attrs["Name"] = "/" + kwargs["name"]
        new.attrs["Config"] = {"Labels": deepcopy(kwargs["labels"])}
        registry[kwargs["name"]] = new
        registry[new.id] = new
        return new

    def remove_new(**kwargs):
        registry.pop(new.attrs.get("Name", "").lstrip("/"), None)
        registry.pop(new.id, None)

    client.containers.get.side_effect = lookup
    client.containers.create.side_effect = create
    client.containers.run.return_value = new
    client.networks.get.side_effect = lambda name: networks[name]
    client.images.pull.return_value.id = "sha256:resolved-new"
    old.rename.side_effect = rename
    new.remove.side_effect = remove_new
    monkeypatch.setattr(docker_client, "get_sync_docker_client", lambda: client)
    monkeypatch.setattr(apps, "_read_self_id", lambda: None)
    monkeypatch.setattr(apps, "get_settings", lambda: SimpleNamespace(DOCKER_HOST="tcp://dockerproxy:2375"))
    monkeypatch.setattr(container_edit.tempfile, "gettempdir", lambda: str(tmp_path))
    wait = MagicMock()
    monkeypatch.setattr(container_edit, "_wait_started", wait)
    return SimpleNamespace(client=client, old=old, new=new, registry=registry, networks=networks, wait=wait, create=create)


def launch(daemon, *, name="original", volumes=None, **overrides):
    arguments = {
        "name": name, "image": "web:stable", "restart_policy": {}, "command": None,
        "ports": {}, "portlabels": {}, "network_mode": None, "network": "private",
        "volumes": {} if volumes is None else volumes, "env": [], "devices": [],
        "labels": {}, "sysctls": {}, "caps": [], "cpus": None,
        "mem_limit": None, "edit": True, "_id": daemon.old.id,
    }
    arguments.update(overrides)
    return _launch_app_sync(**arguments)


def test_success_retains_original_until_replacement_health_and_preserves_data(daemon):
    original_mounts = deepcopy(daemon.old.attrs["Mounts"])

    def healthy(candidate):
        assert candidate is daemon.new
        daemon.old.remove.assert_not_called()
        daemon.new.start.assert_called_once()

    daemon.wait.side_effect = healthy
    result = launch(daemon)
    assert result.container is daemon.new
    daemon.client.containers.run.assert_not_called()
    daemon.old.stop.assert_called_once_with(timeout=30)
    daemon.old.remove.assert_called_once_with(v=False)
    options = daemon.client.containers.create.call_args.kwargs
    assert options["image"] == "sha256:resolved-new"
    assert options["labels"]["local.yachtplus.update.image"] == "web:stable"
    assert options["user"] == "1000:1000" and options["cap_drop"] == ["ALL"]
    assert options["read_only"] is True
    assert options["volumes"]["existing-anonymous-data"] == {"bind": "/data", "mode": "rw"}
    assert options["healthcheck"]["Test"] == ["CMD", "check-health"]
    assert "detach" not in options
    assert options["networking_config"]["private"] == {"Aliases": ["original"], "IPAMConfig": {"IPv4Address": "172.20.0.5"}}
    assert options["networking_config"]["secondary"]["Aliases"] == ["secondary-alias"]
    assert daemon.old.attrs["Mounts"] == original_mounts


@pytest.mark.parametrize("failure", ["pull", "create", "start", "health"])
def test_failed_edit_restores_original_name_networks_and_running_state(daemon, failure):
    if failure == "pull":
        daemon.client.images.pull.side_effect = RuntimeError("pull failed")
    elif failure == "create":
        daemon.client.containers.create.side_effect = RuntimeError("create failed")
    elif failure == "start":
        daemon.new.start.side_effect = RuntimeError("start failed")
    else:
        daemon.wait.side_effect = RuntimeError("unhealthy")
    with pytest.raises(HTTPException) as error:
        launch(daemon)
    assert error.value.status_code == 502
    daemon.old.remove.assert_not_called()
    if failure == "pull":
        daemon.old.stop.assert_not_called()
        daemon.old.rename.assert_not_called()
    else:
        assert daemon.old.attrs["Name"] == "/original"
        daemon.old.start.assert_called_once()
        daemon.networks["private"].connect.assert_called_once_with(daemon.old, aliases=["original"], ipv4_address="172.20.0.5")
        daemon.networks["secondary"].connect.assert_called_once_with(daemon.old, aliases=["secondary-alias"], driver_opt={"foo": "bar"})
    if failure in ("start", "health"):
        daemon.new.remove.assert_called_once_with(force=True, v=False)


def test_failed_rename_edit_restores_actual_old_name(daemon):
    daemon.new.start.side_effect = RuntimeError("failed")
    with pytest.raises(HTTPException):
        launch(daemon, name="renamed")
    assert daemon.old.attrs["Name"] == "/original"
    assert daemon.old.rename.call_args.args == ("original",)
    assert "renamed" not in daemon.registry


def test_colliding_requested_name_never_stops_or_deletes_other_container(daemon):
    unrelated = MagicMock(id="c" * 64)
    daemon.registry["renamed"] = unrelated
    with pytest.raises(HTTPException) as error:
        launch(daemon, name="renamed")
    assert error.value.status_code == 409
    daemon.old.stop.assert_not_called()
    unrelated.remove.assert_not_called()
    daemon.client.containers.create.assert_not_called()


@pytest.mark.parametrize("failure", [docker.errors.APIError("unavailable"), RuntimeError("transport failed")])
def test_original_lookup_failure_never_becomes_new_deployment(daemon, failure):
    daemon.client.containers.get.side_effect = failure
    with pytest.raises((HTTPException, RuntimeError)):
        launch(daemon)
    daemon.client.containers.run.assert_not_called()
    daemon.client.containers.create.assert_not_called()
    daemon.old.stop.assert_not_called()


def test_not_found_original_becomes_normal_new_deployment(daemon):
    daemon.client.containers.get.side_effect = docker.errors.NotFound("missing original")
    result = launch(daemon)
    assert result.container is daemon.new
    daemon.client.containers.run.assert_called_once()
    daemon.client.containers.create.assert_not_called()
    daemon.old.stop.assert_not_called()


@pytest.mark.parametrize("overrides", [
    {"container_user": "0"}, {"caps": ["SYS_ADMIN"]}, {"caps": ["NET_ADMIN"]},
    {"devices": ["/dev/sda:/dev/sda:rwm"]}, {"network_mode": "host"},
])
def test_invalid_profile_options_fail_before_any_daemon_mutation(daemon, overrides):
    with pytest.raises(HTTPException) as error:
        launch(daemon, **overrides)
    assert error.value.status_code == 422
    daemon.client.containers.get.assert_not_called()
    daemon.old.stop.assert_not_called()
    daemon.client.containers.create.assert_not_called()


def test_explicit_replacement_volume_mapping_is_respected(daemon):
    launch(daemon, volumes={"replacement-data": {"bind": "/data", "mode": "ro"}})
    assert daemon.client.containers.create.call_args.kwargs["volumes"] == {"replacement-data": {"bind": "/data", "mode": "ro"}}
    daemon.old.remove.assert_called_once_with(v=False)


def test_stopped_original_stays_stopped_on_rollback(daemon):
    daemon.old.attrs["State"]["Running"] = False
    daemon.wait.side_effect = RuntimeError("unhealthy")
    with pytest.raises(HTTPException):
        launch(daemon)
    daemon.old.stop.assert_not_called()
    daemon.old.start.assert_not_called()
    assert daemon.old.attrs["Name"] == "/original"


@pytest.mark.parametrize("secondary_failure", ["remove replacement", "reconnect network"])
def test_rollback_continues_after_secondary_failure(daemon, secondary_failure):
    daemon.wait.side_effect = RuntimeError("unhealthy")
    if secondary_failure == "remove replacement":
        daemon.new.remove.side_effect = RuntimeError("remove failed")
    else:
        daemon.networks["private"].connect.side_effect = RuntimeError("connect failed")
    with pytest.raises(HTTPException) as error:
        launch(daemon)
    assert error.value.status_code == 502
    assert "rollback reported errors" in error.value.detail
    daemon.networks["secondary"].connect.assert_called_once()
    daemon.old.start.assert_called_once()
    daemon.old.remove.assert_not_called()


def test_backup_cleanup_failure_does_not_report_failed_successful_edit(daemon):
    daemon.old.remove.side_effect = RuntimeError("cleanup failed")
    assert launch(daemon).container is daemon.new
    daemon.new.remove.assert_not_called()
    assert daemon.old.attrs["Name"].startswith("/original_edit_backup_")


def test_ambiguous_create_response_discovers_only_owned_replacement(daemon):
    def response_lost(**kwargs):
        daemon.create(**kwargs)
        raise RuntimeError("create response lost")

    daemon.client.containers.create.side_effect = response_lost
    with pytest.raises(HTTPException):
        launch(daemon)
    daemon.new.remove.assert_called_once_with(force=True, v=False)
    assert daemon.old.attrs["Name"] == "/original"
    daemon.old.start.assert_called_once()


def test_ambiguous_create_never_removes_unrelated_name_collision(daemon):
    unrelated = MagicMock(id="c" * 64, attrs={"Config": {"Labels": {"local.yachtplus.edit.transaction": "another transaction"}}})

    def collision_after_preflight(**kwargs):
        daemon.registry[kwargs["name"]] = unrelated
        raise RuntimeError("create response failed")

    daemon.client.containers.create.side_effect = collision_after_preflight
    with pytest.raises(HTTPException):
        launch(daemon)
    unrelated.remove.assert_not_called()
    unrelated.stop.assert_not_called()
    daemon.old.remove.assert_not_called()
    daemon.old.start.assert_called_once()


def test_overlapping_edits_rejected_before_stopping_original(daemon):
    with container_edit._edit_lock(daemon.old.id):
        with pytest.raises(HTTPException) as error:
            launch(daemon)
    assert error.value.status_code == 409
    daemon.old.reload.assert_not_called()
    daemon.old.stop.assert_not_called()


def test_existing_auto_remove_rejected_before_stopping_original(daemon):
    daemon.old.attrs["HostConfig"]["AutoRemove"] = True
    with pytest.raises(HTTPException) as error:
        launch(daemon)
    assert error.value.status_code == 409
    daemon.old.stop.assert_not_called()
    daemon.client.containers.create.assert_not_called()


def test_same_original_volume_at_multiple_targets_is_preserved(daemon):
    daemon.old.attrs["Mounts"].append({"Type": "volume", "Name": "existing-anonymous-data", "Destination": "/backup", "RW": False})
    launch(daemon)
    options = daemon.client.containers.create.call_args.kwargs
    assert options["volumes"]["existing-anonymous-data"]["bind"] == "/data"
    assert options["mounts"] == [{"Target": "/backup", "Source": "existing-anonymous-data", "Type": "volume", "ReadOnly": True}]


def test_requested_source_at_new_target_is_not_overwritten(daemon):
    launch(daemon, volumes={"existing-anonymous-data": {"bind": "/different-target", "mode": "rw"}})
    options = daemon.client.containers.create.call_args.kwargs
    assert options["volumes"]["existing-anonymous-data"]["bind"] == "/different-target"
    assert options["mounts"][0]["Target"] == "/data"


def test_missing_original_deploy_error_does_not_delete_unrelated_container(daemon):
    unrelated = MagicMock(id="c" * 64, attrs={"Config": {"Labels": {}}})

    def lookup(identifier):
        if identifier == daemon.old.id:
            raise docker.errors.NotFound("original absent")
        return unrelated

    response = SimpleNamespace(status_code=500, reason="Internal server error")
    daemon.client.containers.get.side_effect = lookup
    daemon.client.containers.run.side_effect = docker.errors.APIError("start failed", response=response)
    with pytest.raises(HTTPException):
        launch(daemon)
    unrelated.remove.assert_not_called()


def test_missing_original_deploy_error_cleans_only_its_created_container(daemon):
    response = SimpleNamespace(status_code=500, reason="Internal server error")

    def lookup(identifier):
        if identifier == daemon.old.id:
            raise docker.errors.NotFound("original absent")
        return daemon.new

    def run_error(**kwargs):
        daemon.new.attrs["Config"] = {"Labels": kwargs["labels"]}
        raise docker.errors.APIError("start failed", response=response)

    daemon.client.containers.get.side_effect = lookup
    daemon.client.containers.run.side_effect = run_error
    with pytest.raises(HTTPException):
        launch(daemon)
    daemon.new.remove.assert_called_once_with(force=True, v=False)


@pytest.mark.parametrize("role", ["application", "docker-proxy", "fail2ban"])
def test_managed_infrastructure_cannot_be_edited_as_workload(daemon, role):
    daemon.old.attrs["Config"]["Labels"] = {"local.yachtplus.infrastructure": role}
    with pytest.raises(HTTPException) as error:
        launch(daemon)
    assert error.value.status_code == 409
    daemon.old.stop.assert_not_called()
    daemon.client.images.pull.assert_not_called()
    daemon.client.containers.create.assert_not_called()


@pytest.mark.parametrize("identity", ["a" * 12, "a" * 64])
def test_yacht_self_id_guard_protects_legacy_unlabelled_app(daemon, monkeypatch, identity):
    monkeypatch.setattr(apps, "_read_self_id", lambda: identity)
    with pytest.raises(HTTPException) as error:
        launch(daemon)
    assert error.value.status_code == 409
    daemon.old.stop.assert_not_called()
    daemon.client.images.pull.assert_not_called()


@pytest.mark.parametrize("identity", ["container_name", "network_alias", "network_ip", "network_dns_name"])
def test_configured_docker_proxy_guard_protects_legacy_unlabelled_proxy(daemon, monkeypatch, identity):
    if identity == "container_name":
        host = "original"
    elif identity == "network_alias":
        host = "legacyproxy"
        daemon.old.attrs["NetworkSettings"]["Networks"]["private"]["Aliases"].append(host)
    elif identity == "network_dns_name":
        host = "legacyproxy"
        daemon.old.attrs["NetworkSettings"]["Networks"]["private"]["DNSNames"] = [host]
    else:
        host = "172.20.0.5"
        daemon.old.attrs["NetworkSettings"]["Networks"]["private"]["IPAddress"] = host
    monkeypatch.setattr(apps, "get_settings", lambda: SimpleNamespace(DOCKER_HOST=f"tcp://{host}:2375"))
    with pytest.raises(HTTPException) as error:
        launch(daemon)
    assert error.value.status_code == 409
    daemon.old.stop.assert_not_called()
    daemon.client.containers.create.assert_not_called()
