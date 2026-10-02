"""Non-follow container logs are an awaitable list in aiodocker."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.actions import containers


def _mock_docker(monkeypatch):
    docker = MagicMock()
    docker.close = AsyncMock()
    container = MagicMock()
    container.log = AsyncMock(return_value=["first", "second"])
    docker.containers.get = AsyncMock(return_value=container)
    monkeypatch.setattr(containers.aiodocker, "Docker", lambda **kwargs: docker)
    return docker, container


@pytest.mark.asyncio
async def test_get_logs_awaits_non_follow_result(monkeypatch):
    docker, container = _mock_docker(monkeypatch)

    result = await containers.get_logs("abc", tail=20, timestamps=True, since=10)

    assert result == ["first", "second"]
    container.log.assert_awaited_once_with(
        stdout=True, stderr=True, follow=False, tail=20, timestamps=True, since=10
    )
    docker.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_non_follow_log_generator_yields_all_lines(monkeypatch):
    docker, container = _mock_docker(monkeypatch)

    result = [event async for event in containers.get_logs_generator("abc", follow=False)]

    assert result == [{"data": "first"}, {"data": "second"}, {"event": "end", "data": "Log stream ended"}]
    container.log.assert_awaited_once()
    docker.close.assert_awaited_once_with()
