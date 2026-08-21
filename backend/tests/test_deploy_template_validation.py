"""Regression for BUG-101: the deploy endpoint passed the user-supplied
DeployForm through to the docker daemon almost unchanged. Pydantic
checked types; nothing enforced semantic validity. A `perm_start` user
could (a) set network_mode=container:<other-tenant-id> to jump
namespaces, (b) request CAP_SYS_ADMIN / CAP_SYS_MODULE, or (c)
bind-mount /var/run/docker.sock to get root on the host.

The fix funnels every deploy through _validate_deploy_template before
any daemon call.
"""
import pytest
from fastapi import HTTPException

from api.routers.apps import _validate_deploy_template
from api.db.schemas.apps import (
    DeployForm,
    VolumesSchema,
    DevicesSchema,
)


def _form(**kwargs) -> DeployForm:
    base = {"name": "ok", "image": "nginx:latest"}
    base.update(kwargs)
    return DeployForm(**base)


def test_accepts_minimal_valid_template():
    _validate_deploy_template(_form())  # no raise


def test_rejects_invalid_name_with_slash():
    with pytest.raises(HTTPException) as exc:
        _validate_deploy_template(_form(name="evil/../name"))
    assert exc.value.status_code == 422


def test_rejects_empty_image():
    with pytest.raises(HTTPException) as exc:
        _validate_deploy_template(_form(image="   "))
    assert exc.value.status_code == 422


def test_rejects_image_with_shell_metachars():
    for bad in ("nginx;rm -rf /", "nginx | wget", "nginx`id`", "nginx$PATH"):
        with pytest.raises(HTTPException):
            _validate_deploy_template(_form(image=bad))


def test_rejects_oversize_image_reference():
    with pytest.raises(HTTPException) as exc:
        _validate_deploy_template(_form(image="r/" + "x" * 600))
    assert exc.value.status_code == 422


def test_rejects_container_namespace_jump():
    with pytest.raises(HTTPException) as exc:
        _validate_deploy_template(_form(network_mode="container:abc123"))
    assert exc.value.status_code == 422


def test_accepts_known_network_modes():
    for mode in ("bridge", "host", "none", "default"):
        _validate_deploy_template(_form(network_mode=mode))


def test_rejects_dangerous_capability():
    for cap in ("SYS_ADMIN", "CAP_SYS_MODULE", "ALL", "sys_admin"):
        with pytest.raises(HTTPException) as exc:
            _validate_deploy_template(_form(cap_add=[cap]))
        assert exc.value.status_code == 422


def test_accepts_benign_capability():
    _validate_deploy_template(_form(cap_add=["NET_BIND_SERVICE", "CHOWN"]))


def test_rejects_docker_sock_bind_mount():
    vol = VolumesSchema(container="/var/run/docker.sock", bind="/var/run/docker.sock")
    with pytest.raises(HTTPException) as exc:
        _validate_deploy_template(_form(volumes=[vol]))
    assert exc.value.status_code == 422


def test_rejects_proc_bind_mount():
    vol = VolumesSchema(container="/proc", bind="/proc")
    with pytest.raises(HTTPException) as exc:
        _validate_deploy_template(_form(volumes=[vol]))
    assert exc.value.status_code == 422


def test_rejects_etc_subpath_bind_mount():
    vol = VolumesSchema(container="/etc/shadow", bind="/etc/shadow")
    with pytest.raises(HTTPException):
        _validate_deploy_template(_form(volumes=[vol]))


def test_rejects_sensitive_device_host_path():
    dev = DevicesSchema(container="/dev/sda", host="/proc/kcore")
    with pytest.raises(HTTPException):
        _validate_deploy_template(_form(devices=[dev]))


def test_accepts_legitimate_bind_mount():
    vol = VolumesSchema(container="/data", bind="/srv/yachtplus/data")
    _validate_deploy_template(_form(volumes=[vol]))
