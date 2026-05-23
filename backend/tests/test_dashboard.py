import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from api.routers.dashboard import get_dashboard_stats


class MockAuthValid:
    def jwt_required(self, allow_setup_pending=False):
        return True


class MockAuthInvalid:
    def jwt_required(self, allow_setup_pending=False):
        raise HTTPException(status_code=401, detail="Unauthorized")


def make_disk(total=100, used=40):
    disk = MagicMock()
    disk.total = total
    disk.used = used
    return disk


def make_mem(percent=50.0, total=8_000_000_000, used=4_000_000_000):
    mem = MagicMock()
    mem.percent = percent
    mem.total = total
    mem.used = used
    return mem


@pytest.mark.asyncio
async def test_get_dashboard_stats_returns_expected_structure():
    with patch("api.routers.dashboard.psutil.cpu_percent", return_value=12.5), \
         patch("api.routers.dashboard.psutil.virtual_memory", return_value=make_mem(percent=33.3, total=16_000_000_000, used=4_000_000_000)), \
         patch("api.routers.dashboard.shutil.disk_usage", return_value=make_disk(total=1000, used=250)):

        result = await get_dashboard_stats(Authorize=MockAuthValid())

    assert result["info"] == {"status": "active"}
    assert result["resources"]["cpu"] == 12.5
    assert result["resources"]["ram"] == 33.3
    assert result["resources"]["ram_total"] == 16_000_000_000
    assert result["resources"]["ram_used"] == 4_000_000_000
    assert result["resources"]["disk"] == 25.0
    assert result["resources"]["disk_total"] == 1000
    assert result["resources"]["disk_used"] == 250


@pytest.mark.asyncio
async def test_get_dashboard_stats_rounds_disk_to_one_decimal():
    # 333/999 = 33.3333... -> 33.3
    with patch("api.routers.dashboard.psutil.cpu_percent", return_value=0.0), \
         patch("api.routers.dashboard.psutil.virtual_memory", return_value=make_mem()), \
         patch("api.routers.dashboard.shutil.disk_usage", return_value=make_disk(total=999, used=333)):

        result = await get_dashboard_stats(Authorize=MockAuthValid())

    assert result["resources"]["disk"] == 33.3


@pytest.mark.asyncio
async def test_get_dashboard_stats_handles_zero_cpu():
    with patch("api.routers.dashboard.psutil.cpu_percent", return_value=0.0), \
         patch("api.routers.dashboard.psutil.virtual_memory", return_value=make_mem(percent=0.0)), \
         patch("api.routers.dashboard.shutil.disk_usage", return_value=make_disk()):

        result = await get_dashboard_stats(Authorize=MockAuthValid())

    assert result["resources"]["cpu"] == 0.0
    assert result["resources"]["ram"] == 0.0


@pytest.mark.asyncio
async def test_get_dashboard_stats_unauthorized():
    auth = MockAuthInvalid()
    with pytest.raises(HTTPException) as exc:
        await get_dashboard_stats(Authorize=auth)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_dashboard_stats_calls_psutil_and_shutil():
    with patch("api.routers.dashboard.psutil.cpu_percent") as cpu_mock, \
         patch("api.routers.dashboard.psutil.virtual_memory") as mem_mock, \
         patch("api.routers.dashboard.shutil.disk_usage") as disk_mock:

        cpu_mock.return_value = 1.0
        mem_mock.return_value = make_mem()
        disk_mock.return_value = make_disk()

        await get_dashboard_stats(Authorize=MockAuthValid())

    cpu_mock.assert_called_once()
    mem_mock.assert_called_once()
    disk_mock.assert_called_once_with("/")
