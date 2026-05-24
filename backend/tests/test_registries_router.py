"""Regression for the wall of `Error fetching dockerhub/ghcr/linuxserver`
404s in the browser console when opening the Templates page.

The frontend (RegistryBrowser.vue, ApplicationsForm.vue) calls three
registry endpoints that didn't exist on the router:
  GET /api/registries/popular?registry=<r>
  GET /api/registries/tags?image=<i>&registry=<r>
  GET /api/registries/inspect?image=<i>
The util module exposed the functions; only the HTTP wiring was missing.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.routers.registries import popular_images, image_tags, inspect_image


class MockAuth:
    def jwt_required(self, allow_setup_pending=False):
        return True

    def get_jwt_subject(self, allow_setup_pending=False):
        return "admin"


@pytest.mark.asyncio
async def test_popular_images_forwards_to_util():
    with patch(
        "api.routers.registries.registry_utils.get_popular_images",
        new=AsyncMock(return_value=[{"name": "nginx"}]),
    ) as inner:
        result = await popular_images(registry="dockerhub", Authorize=MockAuth())
    inner.assert_awaited_once_with("dockerhub")
    assert result == [{"name": "nginx"}]


@pytest.mark.asyncio
async def test_image_tags_forwards_to_util():
    with patch(
        "api.routers.registries.registry_utils.get_image_tags",
        new=AsyncMock(return_value=["latest", "1.25"]),
    ) as inner:
        result = await image_tags(image="nginx", registry="dockerhub", Authorize=MockAuth())
    inner.assert_awaited_once_with("dockerhub", "nginx")
    assert result == ["latest", "1.25"]


@pytest.mark.asyncio
async def test_image_tags_rejects_empty_image():
    """An empty `image` parameter must short-circuit to [] — without this
    the util would do `library/` (trailing slash) and DockerHub 404s."""
    result = await image_tags(image="   ", registry="dockerhub", Authorize=MockAuth())
    assert result == []


@pytest.mark.asyncio
async def test_inspect_empty_image_returns_empty_dict():
    result = await inspect_image(image="", Authorize=MockAuth())
    assert result == {}


@pytest.mark.asyncio
async def test_inspect_returns_empty_on_registry_error():
    """Registry outages must surface as an empty dict, not a 500 — the
    deploy form only uses this to pre-fill optional fields."""
    with patch(
        "api.routers.registries.registry_utils.fetch_dockerhub_image_info",
        side_effect=RuntimeError("dockerhub down"),
    ):
        result = await inspect_image(image="nginx", Authorize=MockAuth())
    assert result == {}


@pytest.mark.asyncio
async def test_inspect_returns_metadata_when_available():
    with patch(
        "api.routers.registries.registry_utils.fetch_dockerhub_image_info",
        new=AsyncMock(return_value={"description": "web server", "pulls": 1000}),
    ):
        result = await inspect_image(image="nginx", Authorize=MockAuth())
    assert result["description"] == "web server"
    assert result["pulls"] == 1000
