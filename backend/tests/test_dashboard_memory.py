"""N-20: Dashboard memory should prefer cgroup container limits over host RAM."""

import asyncio
import pytest
from unittest.mock import patch, MagicMock

from api.actions import dashboard


def test_read_cgroup_v2_memory_stats():
    fake_files = {
        "/sys/fs/cgroup/memory.current": "1073741824",
        "/sys/fs/cgroup/memory.max": "2147483648",
    }

    def fake_open(path, mode):
        return MagicMock(
            __enter__=lambda s: s,
            __exit__=lambda *a: None,
            read=lambda: fake_files.get(path, ""),
        )

    with patch("os.path.exists", side_effect=lambda p: p in fake_files):
        with patch("builtins.open", fake_open):
            stats = dashboard._read_cgroup_memory_stats()

    assert stats["usage"] == 1073741824
    assert stats["limit"] == 2147483648


@pytest.mark.asyncio
async def test_get_container_memory_uses_cgroup():
    with patch.object(dashboard, "_read_cgroup_memory_stats", return_value={"limit": 2_000_000_000, "usage": 1_000_000_000}):
        result = await dashboard._get_container_memory()
        assert result["source"] == "cgroup"
        assert result["ram_total"] == 2_000_000_000
        assert result["ram_used"] == 1_000_000_000
        assert result["ram"] == 50.0


@pytest.mark.asyncio
async def test_get_container_memory_falls_back_to_psutil(monkeypatch):
    monkeypatch.setattr(dashboard, "_read_cgroup_memory_stats", lambda: {})
    class _Mem:
        percent = 42.0
        total = 16_000_000_000
        used = 6_720_000_000
    with patch.object(dashboard.psutil, "virtual_memory", return_value=_Mem()):
        result = await dashboard._get_container_memory()
        assert result["source"] == "psutil"
