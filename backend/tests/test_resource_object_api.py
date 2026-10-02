"""Exercise aiodocker resource object methods used by detail and delete actions."""

from unittest.mock import AsyncMock, MagicMock
from aiodocker.containers import DockerContainer
from fastapi import HTTPException

import pytest

from api.actions import resources


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['images', 'volumes', 'networks'])
async def test_resource_usage_recognizes_real_aiodocker_container_objects(monkeypatch, kind):
    docker = _docker_context()
    docker.containers.list = AsyncMock(return_value=[DockerContainer(
        docker, Id='container', ImageID='image', Mounts=[{'Type': 'volume', 'Name': 'data'}],
        NetworkSettings={'Networks': {'app': {'NetworkID': 'network'}}},
    )])
    docker.images.list = AsyncMock(return_value=[{'Id': 'image'}])
    docker.volumes.list = AsyncMock(return_value={'Volumes': [{'Name': 'data'}]})
    docker.networks.list = AsyncMock(return_value=[{'Id': 'network'}])
    monkeypatch.setattr(resources.aiodocker, 'Docker', lambda **kwargs: docker)

    result = await getattr(resources, f'get_{kind}')()

    assert result['items'][0]['inUse'] is True


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['images', 'volumes', 'networks'])
async def test_failed_container_inventory_is_not_displayed_as_unused(monkeypatch, kind):
    docker = _docker_context()
    docker.containers.list = AsyncMock(side_effect=RuntimeError('daemon unavailable'))
    docker.images.list = AsyncMock(return_value=[])
    docker.volumes.list = AsyncMock(return_value={'Volumes': []})
    docker.networks.list = AsyncMock(return_value=[])
    monkeypatch.setattr(resources.aiodocker, 'Docker', lambda **kwargs: docker)

    with pytest.raises(HTTPException) as raised:
        await getattr(resources, f'get_{kind}')()

    assert raised.value.status_code == 503


def _docker_context():
    docker = MagicMock()
    docker.__aenter__ = AsyncMock(return_value=docker)
    docker.__aexit__ = AsyncMock(return_value=False)
    return docker


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("nginx", "nginx:latest"),
        ("nginx:1.27", "nginx:1.27"),
        ("registry.example:5000/team/app", "registry.example:5000/team/app:latest"),
        ("registry.example:5000/team/app:1.2", "registry.example:5000/team/app:1.2"),
        ("team/app@sha256:abc123", "team/app@sha256:abc123"),
    ],
)
async def test_write_image_preserves_registry_port_and_digest(monkeypatch, image, expected):
    docker = _docker_context()
    docker.images.pull = AsyncMock()
    monkeypatch.setattr(resources.aiodocker, "Docker", lambda **kwargs: docker)
    monkeypatch.setattr(resources, "get_images", AsyncMock(return_value={"items": [], "total": 0}))

    await resources.write_image(image)

    docker.images.pull.assert_awaited_once_with(expected)


@pytest.mark.asyncio
async def test_get_volume_uses_volume_object_show(monkeypatch):
    docker = _docker_context()
    docker._query_json = AsyncMock(return_value={"Name": "data"})
    docker.volumes = MagicMock(spec=["list", "create"])
    docker.containers.list = AsyncMock(return_value=[])
    monkeypatch.setattr(resources.aiodocker, "Docker", lambda **kwargs: docker)

    result = await resources.get_volume("data")

    docker._query_json.assert_awaited_once_with("volumes/data")
    assert result == {"Name": "data", "inUse": False}


@pytest.mark.asyncio
async def test_delete_volume_uses_volume_object_delete(monkeypatch):
    docker = _docker_context()
    docker._query_json = AsyncMock(return_value={"Name": "data"})
    docker.volumes = MagicMock(spec=["list", "create"])
    monkeypatch.setattr(resources.aiodocker, "Docker", lambda **kwargs: docker)

    result = await resources.delete_volume("data")

    docker._query_json.assert_awaited_once_with("volumes/data")
    docker._query.assert_called_once()
    assert docker._query.call_args.args[0] == "volumes/data"
    assert docker._query.call_args.kwargs["method"] == "DELETE"
    assert result == {"Name": "data"}


@pytest.mark.asyncio
async def test_delete_network_uses_network_object_delete(monkeypatch):
    docker = _docker_context()
    network = MagicMock()
    network.show = AsyncMock(return_value={"Id": "net-1"})
    network.delete = AsyncMock()
    docker.networks = MagicMock(spec=["get"])
    docker.networks.get = AsyncMock(return_value=network)
    monkeypatch.setattr(resources.aiodocker, "Docker", lambda **kwargs: docker)

    result = await resources.delete_network("net-1")

    docker.networks.get.assert_awaited_once_with("net-1")
    network.show.assert_awaited_once_with()
    network.delete.assert_awaited_once_with()
    assert result == {"Id": "net-1"}
