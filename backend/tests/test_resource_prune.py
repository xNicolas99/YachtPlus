"""Prune calls use Engine endpoints supported by the installed aiodocker."""
import json
from unittest.mock import AsyncMock, MagicMock

import aiodocker
import pytest
from fastapi import HTTPException

from api.actions import resources


def docker_context(monkeypatch, result=None, error=None):
    client = MagicMock(spec=aiodocker.Docker)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client._query_json = AsyncMock(return_value=result, side_effect=error)
    monkeypatch.setattr(resources.aiodocker, "Docker", lambda **kwargs: client)
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize("resource,path", [
    ("images", "images/prune"), ("networks", "networks/prune"),
    ("volumes", "volumes/prune"), ("containers", "containers/prune"),
    ("build_cache", "build/prune"),
])
async def test_prune_uses_engine_endpoint_and_preserves_result(monkeypatch, resource, path):
    result = {"SpaceReclaimed": 2048}
    client = docker_context(monkeypatch, result=result)
    assert await resources.prune_resources(resource) == result
    params = {"filters": json.dumps({"dangling": ["false"]})} if resource == "images" else {}
    client._query_json.assert_awaited_once_with(path, method="POST", params=params)


@pytest.mark.asyncio
@pytest.mark.parametrize("error,status", [
    (aiodocker.exceptions.DockerError(409, "in use"), 409),
    (RuntimeError("private daemon detail"), 503),
])
async def test_prune_failure_is_not_reported_as_success(monkeypatch, error, status):
    docker_context(monkeypatch, error=error)
    with pytest.raises(HTTPException) as raised:
        await resources.prune_resources("volumes")
    assert raised.value.status_code == status
    assert "private daemon detail" not in raised.value.detail


@pytest.mark.asyncio
async def test_unknown_resource_never_contacts_docker(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(resources.aiodocker, "Docker", factory)
    with pytest.raises(HTTPException) as raised:
        await resources.prune_resources("invalid")
    assert raised.value.status_code == 422
    factory.assert_not_called()
