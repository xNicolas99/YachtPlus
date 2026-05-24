"""Regression for BUG-006: deploy_app collapsed every failure into a
500 with str(exc) in the body, regardless of whether the underlying
cause was a 4xx (no such image, name conflict) or an actual server
fault. That was confusing to operators and leaked daemon details.

The fix maps docker-py APIError to its real status_code + explanation,
maps aiodocker DockerError similarly, and otherwise returns a generic
"Deploy failed" with the full traceback in the server log.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
import docker.errors
import aiodocker.exceptions

from api.actions.apps import deploy_app
from api.db.schemas.apps import DeployForm


def _form(**kwargs):
    base = {"name": "ok", "image": "nginx:latest"}
    base.update(kwargs)
    return DeployForm(**base)


@pytest.mark.asyncio
async def test_docker_apierror_status_propagated():
    """docker-py APIError carries status_code + explanation — pass them
    through so the frontend sees the right 4xx, not 500-with-stack."""
    # APIError exposes status_code as a read-only property derived from
    # the wrapped response — construct one with a Mock response so the
    # property returns 409. explanation is settable.
    fake_response = MagicMock()
    fake_response.status_code = 409
    err = docker.errors.APIError(
        "conflict",
        response=fake_response,
        explanation="Container name already in use",
    )

    with patch("api.actions.apps.check_container_conflicts", return_value=[]), \
         patch("api.actions.apps.launch_app", side_effect=err):
        with pytest.raises(HTTPException) as exc:
            await deploy_app(_form())
    assert exc.value.status_code == 409
    assert "already in use" in exc.value.detail


@pytest.mark.asyncio
async def test_aiodocker_dockererror_status_propagated():
    err = aiodocker.exceptions.DockerError(404, {"message": "no such image"})
    with patch("api.actions.apps.check_container_conflicts", return_value=[]), \
         patch("api.actions.apps.launch_app", side_effect=err):
        with pytest.raises(HTTPException) as exc:
            await deploy_app(_form())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_unknown_error_does_not_leak_message():
    SECRET = "/var/lib/docker/internal/path"
    with patch("api.actions.apps.check_container_conflicts", return_value=[]), \
         patch("api.actions.apps.launch_app", side_effect=RuntimeError(SECRET)):
        with pytest.raises(HTTPException) as exc:
            await deploy_app(_form())
    assert exc.value.status_code == 500
    assert SECRET not in str(exc.value.detail)
    assert exc.value.detail == "Deploy failed"


@pytest.mark.asyncio
async def test_log_fetch_failure_does_not_500_a_successful_deploy():
    """If the container is up but `launch.log(...)` blows up afterwards
    (race, container exited cleanly etc.), return success with an empty
    log body — the deploy itself succeeded.
    """
    fake_launch = MagicMock()
    async def boom(*a, **kw):
        raise RuntimeError("log fetch failed")
    fake_launch.log = boom

    with patch("api.actions.apps.check_container_conflicts", return_value=[]), \
         patch("api.actions.apps.launch_app", return_value=fake_launch):
        result = await deploy_app(_form())
    # DeployLogs Pydantic model: .logs should be empty string from "".join([])
    assert getattr(result, "logs", None) == ""
