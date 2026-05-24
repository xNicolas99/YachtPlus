"""Regression for BUG-103: stream_stats_generator opened
`container.stats(stream=True)` and never explicitly aclose()'d the
async iterator on client disconnect. The underlying aiohttp response
stayed open until GC ran. It also caught CancelledError under a broad
`except Exception` and turned a normal disconnect into a logged error.

The fix:
  - hold a reference to the stats iterator, aclose() it in finally,
  - re-raise asyncio.CancelledError (don't treat client disconnect as
    an error to log + yield),
  - yield a generic "stats stream error" instead of the raw exception
    message (which could include daemon paths or container IDs).
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.actions.containers import stream_stats_generator


def _request(disconnected=False):
    r = MagicMock()
    r.is_disconnected = AsyncMock(return_value=disconnected)
    return r


class _FakeStatsIter:
    """Async-iterator that yields a fixed list of frames then ends.
    Exposes an aclose() spy so the test can assert cleanup happened.
    """
    def __init__(self, frames):
        self._frames = list(frames)
        self.aclose = AsyncMock()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._frames:
            raise StopAsyncIteration
        return self._frames.pop(0)


def _stats_frame():
    return {
        "memory_stats": {"usage": 1024, "limit": 4096},
        "cpu_stats": {
            "cpu_usage": {"total_usage": 200},
            "system_cpu_usage": 1000,
            "online_cpus": 2,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 100},
            "system_cpu_usage": 500,
        },
    }


def _docker_patch(stats_iter):
    container = MagicMock()
    container.stats = MagicMock(return_value=stats_iter)
    docker_instance = MagicMock()
    docker_instance.containers = MagicMock()
    docker_instance.containers.get = AsyncMock(return_value=container)
    docker_instance.__aenter__ = AsyncMock(return_value=docker_instance)
    docker_instance.__aexit__ = AsyncMock(return_value=False)
    return patch("api.actions.containers.aiodocker.Docker", return_value=docker_instance)


@pytest.mark.asyncio
async def test_stats_iterator_is_closed_on_disconnect():
    # Two frames available: the consumer yields the first, then on the
    # second pass is_disconnected returns True and the loop breaks. The
    # `finally` block in stream_stats_generator must then aclose() the
    # iterator we returned — this is what the test asserts.
    stats_iter = _FakeStatsIter([_stats_frame(), _stats_frame()])
    request = _request()
    request.is_disconnected = AsyncMock(side_effect=[False, True])

    with _docker_patch(stats_iter):
        gen = stream_stats_generator(request, "abc")
        first = await gen.__anext__()
        assert first["event"] == "stats"
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
    stats_iter.aclose.assert_awaited()


@pytest.mark.asyncio
async def test_stats_iterator_is_closed_when_iterator_ends():
    """When the underlying stats stream ends naturally (container died),
    aclose() must still be called from the finally block."""
    stats_iter = _FakeStatsIter([])
    request = _request()
    with _docker_patch(stats_iter):
        gen = stream_stats_generator(request, "abc")
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
    stats_iter.aclose.assert_awaited()


@pytest.mark.asyncio
async def test_generic_error_payload_does_not_leak_exception_message():
    SECRET = "OCI runtime exec failed at /var/lib/docker/secret"

    class BoomIter:
        aclose = AsyncMock()

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise RuntimeError(SECRET)

    request = _request(disconnected=False)
    with _docker_patch(BoomIter()):
        gen = stream_stats_generator(request, "abc")
        event = await gen.__anext__()
    assert event["event"] == "error"
    assert SECRET not in event["data"]
    assert event["data"] == "stats stream error"


@pytest.mark.asyncio
async def test_cancellation_propagates_without_swallowing():
    """A client cancelling the SSE connection must propagate as
    CancelledError, not be turned into an error frame."""
    class HangIter:
        aclose = AsyncMock()

        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.sleep(3600)
            raise StopAsyncIteration

    request = _request(disconnected=False)
    with _docker_patch(HangIter()):
        gen = stream_stats_generator(request, "abc")
        task = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
