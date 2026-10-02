"""The log dialog's SSE request must reach Docker with its display options."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from api.actions import containers as log_actions
from api.routers import containers


@pytest.mark.asyncio
@pytest.mark.parametrize("timestamps", [True, False])
async def test_follow_logs_streams_lines_with_requested_options(monkeypatch, timestamps):
    auth_check = AsyncMock()
    permission_check = AsyncMock()
    monkeypatch.setattr(containers, "auth_check", auth_check)
    monkeypatch.setattr(containers, "check_permission", permission_check)

    async def log_lines():
        yield "first line"
        yield "second line"

    container = MagicMock()
    container.log.return_value = log_lines()
    docker = MagicMock()
    docker.containers.get = AsyncMock(return_value=container)
    docker.close = AsyncMock()
    monkeypatch.setattr(log_actions.aiodocker, "Docker", lambda **kwargs: docker)
    request = Request({
        "type": "http",
        "query_string": f"follow=true&tail=5000&timestamps={str(timestamps).lower()}".encode(),
    })
    auth, db = MagicMock(), MagicMock()

    response = await containers.get_container_logs(request, "abc", db=db, Authorize=auth)
    events = [event async for event in response.body_iterator]

    assert response.media_type == "text/event-stream"
    assert events == [{"data": "first line"}, {"data": "second line"}, {"event": "end", "data": "Log stream ended"}]
    auth_check.assert_awaited_once_with(auth)
    permission_check.assert_awaited_once_with("perm_start", auth, db)
    container.log.assert_called_once_with(
        stdout=True, stderr=True, follow=True, tail=5000, timestamps=timestamps
    )
    docker.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_non_follow_logs_forwards_tail_since_and_timestamps(monkeypatch):
    monkeypatch.setattr(containers, "auth_check", AsyncMock())
    get_logs = AsyncMock(return_value=["line"])
    monkeypatch.setattr(log_actions, "get_logs", get_logs)
    request = Request({
        "type": "http",
        "query_string": b"tail=500&since=10&timestamps=true",
    })

    response = await containers.get_container_logs(
        request, "abc", db=MagicMock(), Authorize=MagicMock()
    )

    assert response == ["line"]
    get_logs.assert_awaited_once_with("abc", tail=500, since="10", timestamps=True)
