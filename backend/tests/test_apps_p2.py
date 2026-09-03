"""Regression test for the P2 backend improvement in actions/apps.py.

- FIX 4: deploy_app handles both synchronous docker SDK errors and aiodocker
  errors uniformly. The synchronous path is still required because
  launch_app/_launch_app_sync run docker-py inside a thread-pool executor.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from api.actions.apps import deploy_app
from api.db.schemas.apps import DeployForm


@pytest.fixture
def deploy_form(monkeypatch):
    # DeployForm imports load_template_variables_async; avoid touching DB.
    from api.utils import apps as utils_apps
    monkeypatch.setattr(utils_apps, "load_template_variables_async", AsyncMock(return_value={}))
    return DeployForm(
        name="testapp",
        image="nginx:latest",
        restart_policy="unless-stopped",
        command=None,
        ports=[],
        network="bridge",
        network_mode=None,
        volumes=[],
        env=[],
        devices=[],
        labels=[],
        sysctls=[],
        cap_add=[],
        cpus=None,
        mem_limit=None,
        edit=False,
    )


@pytest.mark.asyncio
async def test_deploy_app_maps_sync_docker_exception(deploy_form):
    """FIX 4: a synchronous docker.errors.DockerException from the thread
    pool is caught and mapped to an HTTPException with no raw daemon leak."""
    import docker

    with patch("api.actions.apps.check_container_conflicts", new=AsyncMock(return_value=[])), \
         patch("api.actions.apps.launch_app") as mock_launch:
        exc = docker.errors.DockerException("connection refused")
        exc.status = 503
        exc.message = "connection refused"
        mock_launch.side_effect = exc

        with pytest.raises(HTTPException) as exc_info:
            await deploy_app(deploy_form)

    assert exc_info.value.status_code == 503
    assert "connection refused" in exc_info.value.detail


@pytest.mark.asyncio
async def test_deploy_app_maps_aiodocker_error(deploy_form):
    """FIX 4: aiodocker.exceptions.DockerError is caught alongside sync errors."""
    import aiodocker

    with patch("api.actions.apps.check_container_conflicts", new=AsyncMock(return_value=[])), \
         patch("api.actions.apps.launch_app") as mock_launch:
        exc = aiodocker.exceptions.DockerError(409, "conflict")
        mock_launch.side_effect = exc

        with pytest.raises(HTTPException) as exc_info:
            await deploy_app(deploy_form)

    assert exc_info.value.status_code == 409
