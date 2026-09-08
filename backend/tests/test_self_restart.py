"""Tests for B14: self-restart must use a fresh aiodocker client."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import api.actions.apps as apps_actions


@pytest.mark.asyncio
async def test_restart_by_name_opens_own_client():
    """_restart_by_name opens its own Docker client and restarts the
    container by NAME — no dependency on a request-scoped client."""
    mock_container = MagicMock()
    mock_container.restart = AsyncMock()

    mock_docker = MagicMock()
    mock_docker.containers = MagicMock()
    mock_docker.containers.get = AsyncMock(return_value=mock_container)

    async def fake_aenter(self):
        return mock_docker

    async def fake_aexit(self, *args):
        return False

    with patch("api.actions.apps.aiodocker.Docker") as MockDockerCls:
        MockDockerCls.return_value.__aenter__ = fake_aenter
        MockDockerCls.return_value.__aexit__ = fake_aexit

        await apps_actions._restart_by_name("yachtplus", timeout=10)

    mock_docker.containers.get.assert_awaited_once_with("yachtplus")
    mock_container.restart.assert_awaited_once_with(timeout=10)


@pytest.mark.asyncio
async def test_restart_by_name_swallows_errors():
    """A failing restart must be logged, not raise — the task runs after
    the response has been sent; an exception would only log."""
    mock_docker = MagicMock()
    mock_docker.containers = MagicMock()
    mock_docker.containers.get = AsyncMock(side_effect=Exception("daemon gone"))

    async def fake_aenter(self):
        return mock_docker

    async def fake_aexit(self, *args):
        return False

    with patch("api.actions.apps.aiodocker.Docker") as MockDockerCls:
        MockDockerCls.return_value.__aenter__ = fake_aenter
        MockDockerCls.return_value.__aexit__ = fake_aexit

        # Must not raise
        await apps_actions._restart_by_name("ghost")

    mock_docker.containers.get.assert_awaited_once_with("ghost")


@pytest.mark.asyncio
async def test_self_restart_branch_schedules_by_name():
    """The self-restart branch in app_action schedules _restart_by_name
    with the container NAME (not the bound aiodocker object)."""
    captured = {}

    def fake_add_task(fn, *args, **kwargs):
        captured["fn"] = fn
        captured["args"] = args

    fake_background = MagicMock()
    fake_background.add_task = fake_add_task

    container_id = "a" * 64
    mock_container = MagicMock()
    mock_container.show = AsyncMock(return_value={"Id": container_id})

    mock_docker = MagicMock()
    mock_docker.containers = MagicMock()
    mock_docker.containers.get = AsyncMock(return_value=mock_container)

    async def fake_aenter(self):
        return mock_docker

    async def fake_aexit(self, *args):
        return False

    async def fake_get_apps():
        return [{"name": "yachtplus"}]

    # cgroup read yields our own container id -> self-restart branch fires
    mock_aiofiles_file = AsyncMock()
    mock_aiofiles_file.readline = AsyncMock(
        return_value=f"0::/docker/{container_id}\n"
    )
    mock_aiofiles_ctx = MagicMock()
    mock_aiofiles_ctx.__aenter__ = AsyncMock(return_value=mock_aiofiles_file)
    mock_aiofiles_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("api.actions.apps.aiodocker.Docker") as MockDockerCls, \
         patch("aiofiles.open", return_value=mock_aiofiles_ctx), \
         patch("api.actions.apps.get_apps", new=fake_get_apps), \
         patch("api.actions.apps._restart_by_name") as rb_name:
        MockDockerCls.return_value.__aenter__ = fake_aenter
        MockDockerCls.return_value.__aexit__ = fake_aexit

        result = await apps_actions.app_action(
            "yachtplus", "restart", background_tasks=fake_background
        )

    assert result == [{"name": "yachtplus"}]
    # The scheduled task must be restart-by-name with the NAME argument
    assert captured["fn"] is not None
    assert captured["args"] == ("yachtplus",)
    # The dead pattern (passing the bound container object) must be gone
    assert captured["args"] != (mock_container,)