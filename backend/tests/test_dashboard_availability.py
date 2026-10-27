from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.actions import dashboard


@pytest.fixture
def dashboard_sources(monkeypatch):
    docker = MagicMock()
    docker.__aenter__ = AsyncMock(return_value=docker)
    docker.__aexit__ = AsyncMock(return_value=False)
    docker.containers.list = AsyncMock(return_value=[])
    docker.images.list = AsyncMock(return_value=[])
    docker.volumes.list = AsyncMock(return_value={"Volumes": []})
    docker.networks.list = AsyncMock(return_value=[])
    monkeypatch.setattr(dashboard.aiodocker, "Docker", lambda **kwargs: docker)
    monkeypatch.setattr(dashboard.psutil, "cpu_percent", lambda: 0)
    monkeypatch.setattr(dashboard, "_get_container_memory", AsyncMock(return_value={"ram": 0}))
    monkeypatch.setattr(dashboard, "find_yml_files", lambda path: {})
    return docker


@pytest.mark.asyncio
async def test_dashboard_docker_outage_is_not_a_successful_empty_inventory(dashboard_sources):
    dashboard_sources.containers.list.side_effect = RuntimeError("daemon at private-host")
    with pytest.raises(HTTPException) as error:
        await dashboard.get_dashboard_stats()
    assert error.value.status_code == 503
    assert "private-host" not in error.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["images", "volumes", "networks"])
async def test_partial_dashboard_failure_is_explicit(dashboard_sources, source):
    getattr(dashboard_sources, source).list.side_effect = RuntimeError("source unavailable")
    result = await dashboard.get_dashboard_stats()
    assert result["info"]["status"] == "degraded"
    assert result["availability"][source] is False
    assert result["availability"]["containers"] is True


@pytest.mark.asyncio
async def test_genuine_empty_dashboard_inventory_is_available(dashboard_sources):
    result = await dashboard.get_dashboard_stats()
    assert result["containers"]["total"] == 0
    assert all(result["availability"].values())
    assert result["info"]["status"] == "active"
