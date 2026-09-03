"""Regression tests for the P2 backend improvements in routers/resources.py
and actions/resources.py.

- FIX 1: /images/{image_id}/pull is POST, not GET.
- FIX 5: /images/, /volumes/ and /networks/ paginate and expose X-Total-Count.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request

from api.routers import resources as resources_router


class _MockAuth:
    def __init__(self, username="admin"):
        self.username = username

    async def jwt_required(self, allow_setup_pending=False):
        return True

    async def get_jwt_subject(self, allow_setup_pending=False):
        return self.username

    async def auth_check(self):
        return True


def _fake_request():
    req = MagicMock(spec=Request)
    req.client.host = "127.0.0.1"
    return req


@pytest.mark.asyncio
async def test_get_images_pagination_and_total_count_header(monkeypatch):
    """FIX 5: images list is paginated and includes X-Total-Count."""
    items = [{"Id": f"img-{i}"} for i in range(150)]
    monkeypatch.setattr(resources_router.resources, "get_images", AsyncMock(return_value={"items": items[:50], "total": 150}))

    result = await resources_router.get_images(
        request=_fake_request(),
        offset=0,
        limit=50,
        Authorize=_MockAuth(),
    )

    assert result["total"] == 150
    assert len(result["items"]) == 50
    resources_router.resources.get_images.assert_awaited_once_with(offset=0, limit=50)


@pytest.mark.asyncio
async def test_get_volumes_pagination_and_total_count_header(monkeypatch):
    """FIX 5: volumes list is paginated and includes X-Total-Count."""
    items = [{"Name": f"vol-{i}"} for i in range(150)]
    monkeypatch.setattr(resources_router.resources, "get_volumes", AsyncMock(return_value={"items": items[:50], "total": 150}))

    result = await resources_router.get_volumes(
        request=_fake_request(),
        offset=0,
        limit=50,
        Authorize=_MockAuth(),
    )

    assert result["total"] == 150
    assert len(result["items"]) == 50
    resources_router.resources.get_volumes.assert_awaited_once_with(offset=0, limit=50)


@pytest.mark.asyncio
async def test_get_networks_pagination_and_total_count_header(monkeypatch):
    """FIX 5: networks list is paginated and includes X-Total-Count."""
    items = [{"Id": f"net-{i}"} for i in range(150)]
    monkeypatch.setattr(resources_router.resources, "get_networks", AsyncMock(return_value={"items": items[:50], "total": 150}))

    result = await resources_router.get_networks(
        request=_fake_request(),
        offset=0,
        limit=50,
        Authorize=_MockAuth(),
    )

    assert result["total"] == 150
    assert len(result["items"]) == 50
    resources_router.resources.get_networks.assert_awaited_once_with(offset=0, limit=50)


@pytest.mark.asyncio
async def test_pull_image_uses_post():
    """FIX 1: pull_image route is registered as POST, not GET."""
    routes = {r.path: r.methods for r in resources_router.router.routes}
    assert routes.get("/images/{image_id}/pull") == {"POST"}


@pytest.mark.asyncio
async def test_actions_pagination_caps_limit_at_500():
    """FIX 5: limit greater than 500 is clamped to 500 in action layer."""
    from api.actions import resources as actions_resources

    fake_items = [{"Id": f"img-{i}"} for i in range(550)]
    fake_containers = []

    with patch.object(actions_resources, "get_settings", return_value=MagicMock(DOCKER_HOST=None)):
        docker_cm = MagicMock()
        docker_cm.__aenter__ = AsyncMock(return_value=docker_cm)
        docker_cm.__aexit__ = AsyncMock(return_value=False)
        docker_cm.containers.list = AsyncMock(return_value=fake_containers)
        docker_cm.images.list = AsyncMock(return_value=fake_items)

        with patch("api.actions.resources.aiodocker.Docker", return_value=docker_cm):
            result = await actions_resources.get_images(offset=0, limit=1000)

    assert result["total"] == 550
    assert len(result["items"]) == 500
