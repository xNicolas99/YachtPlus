"""Regression for the dashboard router shape mismatch.

The router used to be a stand-alone stub that returned only
`{resources, info}`, so the Home page KPI strip crashed with
`TypeError: can't access property "total", overview.containers is
undefined` on every poll. The router now delegates to
`actions.dashboard.get_dashboard_stats()` for the full aggregated
shape (containers / projects / images / volumes / networks /
resources) and layers disk_usage on top.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from api.routers.dashboard import get_dashboard_stats


class MockAuthValid:
    async def jwt_required(self, allow_setup_pending=False):
        return True


class MockAuthInvalid:
    async def jwt_required(self, allow_setup_pending=False):
        raise HTTPException(status_code=401, detail="Unauthorized")


def make_disk(total=1000, used=250):
    disk = MagicMock()
    disk.total = total
    disk.used = used
    return disk


def _action_stats():
    """The exact full shape the action layer produces — anything missing
    here would re-introduce the original `undefined` TypeError on the
    frontend."""
    return {
        "containers": {"total": 4, "running": 3, "stopped": 1, "unhealthy": 0},
        "projects": {"total": 2, "active": 2, "inactive": 0},
        "images": {"total": 10, "used": 6, "dangling": 2, "total_size": 5_000_000_000},
        "volumes": {"total": 5, "in_use": 4, "unused": 1},
        "networks": {"total": 3, "custom": 1, "default": 2},
        "resources": {"cpu": 12.5, "ram": 33.3, "ram_total": 16_000_000_000, "ram_used": 4_000_000_000},
    }


@pytest.mark.asyncio
async def test_router_returns_full_shape_from_action():
    """Every KPI-strip key MUST be present in the response, with the
    counts the action layer computed."""
    with patch(
        "api.routers.dashboard.dashboard_actions.get_dashboard_stats",
        new=AsyncMock(return_value=_action_stats()),
    ), patch(
        "api.routers.dashboard.shutil.disk_usage",
        return_value=make_disk(total=1000, used=250),
    ):
        result = await get_dashboard_stats(Authorize=MockAuthValid())

    for key in ("containers", "projects", "images", "volumes", "networks"):
        assert key in result, f"missing top-level key {key!r}"
        assert "total" in result[key], f"missing {key}.total"
    assert result["containers"]["total"] == 4
    assert result["projects"]["active"] == 2
    assert result["images"]["total_size"] == 5_000_000_000


@pytest.mark.asyncio
async def test_router_adds_disk_to_resources():
    with patch(
        "api.routers.dashboard.dashboard_actions.get_dashboard_stats",
        new=AsyncMock(return_value=_action_stats()),
    ), patch(
        "api.routers.dashboard.shutil.disk_usage",
        return_value=make_disk(total=1000, used=250),
    ):
        result = await get_dashboard_stats(Authorize=MockAuthValid())

    resources = result["resources"]
    # Action's CPU/RAM preserved …
    assert resources["cpu"] == 12.5
    assert resources["ram"] == 33.3
    # … and disk fields layered in by the router.
    assert resources["disk"] == 25.0
    assert resources["disk_total"] == 1000
    assert resources["disk_used"] == 250


@pytest.mark.asyncio
async def test_router_rounds_disk_pct_to_one_decimal():
    with patch(
        "api.routers.dashboard.dashboard_actions.get_dashboard_stats",
        new=AsyncMock(return_value=_action_stats()),
    ), patch(
        "api.routers.dashboard.shutil.disk_usage",
        return_value=make_disk(total=999, used=333),
    ):
        result = await get_dashboard_stats(Authorize=MockAuthValid())
    assert result["resources"]["disk"] == 33.3


@pytest.mark.asyncio
async def test_router_tolerates_disk_failure():
    """Disk stat is nice-to-have. A failure inside shutil must NOT break
    the KPI strip — the container counts still need to render."""
    with patch(
        "api.routers.dashboard.dashboard_actions.get_dashboard_stats",
        new=AsyncMock(return_value=_action_stats()),
    ), patch(
        "api.routers.dashboard.shutil.disk_usage",
        side_effect=OSError("disk full"),
    ):
        result = await get_dashboard_stats(Authorize=MockAuthValid())
    # disk fields absent / unchanged, but containers etc. still there.
    assert result["containers"]["total"] == 4


@pytest.mark.asyncio
async def test_router_tolerates_zero_total_disk():
    """shutil.disk_usage().total == 0 used to ZeroDivisionError. Now
    short-circuits to 0 instead."""
    with patch(
        "api.routers.dashboard.dashboard_actions.get_dashboard_stats",
        new=AsyncMock(return_value=_action_stats()),
    ), patch(
        "api.routers.dashboard.shutil.disk_usage",
        return_value=make_disk(total=0, used=0),
    ):
        result = await get_dashboard_stats(Authorize=MockAuthValid())
    assert result["resources"]["disk"] == 0


@pytest.mark.asyncio
async def test_get_dashboard_stats_unauthorized():
    auth = MockAuthInvalid()
    with pytest.raises(HTTPException) as exc:
        await get_dashboard_stats(Authorize=auth)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_info_status_active_default_present():
    """When the action layer doesn't return `info`, the router should
    still ship `info: {status: 'active'}` so older frontend code that
    reads it doesn't blow up."""
    skinny = _action_stats()
    skinny.pop("resources", None)  # also robustness: missing resources
    with patch(
        "api.routers.dashboard.dashboard_actions.get_dashboard_stats",
        new=AsyncMock(return_value=skinny),
    ), patch(
        "api.routers.dashboard.shutil.disk_usage",
        return_value=make_disk(),
    ):
        result = await get_dashboard_stats(Authorize=MockAuthValid())
    assert result["info"] == {"status": "active"}
