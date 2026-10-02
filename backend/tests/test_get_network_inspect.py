"""Regression for BUG-002: get_network called docker.networks.inspect(id)
— a method that does not exist on aiodocker's DockerNetworks manager.
Every network-detail page raised AttributeError -> the global 500
handler. The fix uses the idiomatic `.get(id).show()` pattern via the
new _inspect_network helper.
"""
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from api.actions.resources import _inspect_network


@pytest.mark.asyncio
async def test_inspect_network_uses_get_then_show():
    """Two-step contract: docker.networks.get(id) -> .show() returns
    the inspect payload. Previously a direct .inspect() call was used
    and raised AttributeError."""
    network_obj = MagicMock()
    network_obj.show = AsyncMock(return_value={"Id": "abc", "Name": "net"})

    docker = MagicMock()
    docker.networks = MagicMock()
    docker.networks.get = AsyncMock(return_value=network_obj)

    result = await _inspect_network(docker, "abc")
    docker.networks.get.assert_awaited_once_with("abc")
    network_obj.show.assert_awaited_once()
    assert result == {"Id": "abc", "Name": "net"}


@pytest.mark.asyncio
async def test_get_network_does_not_call_inspect_attr():
    """Defensive: the manager should never be hit with a non-existent
    `inspect` attribute. If a future refactor reintroduces the bug,
    this asserts that the attribute access path is dead."""
    network_obj = MagicMock()
    network_obj.show = AsyncMock(return_value={"Id": "abc"})

    docker = MagicMock()
    docker.networks = MagicMock(spec=["get"])  # spec excludes .inspect
    docker.networks.get = AsyncMock(return_value=network_obj)

    await _inspect_network(docker, "abc")  # no AttributeError
