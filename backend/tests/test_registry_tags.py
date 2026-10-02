"""GHCR tag lookup must reject hostile references before making requests."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api.utils.registries import get_image_tags


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("image", "repository"),
    [
        ("owner/image", "owner/image"),
        ("ghcr.io/owner/image:latest", "owner/image"),
        ("https://ghcr.io/owner/image@sha256:" + "a" * 64, "owner/image"),
        ("ghcr.io/owner/sub-project/image_1.2:stable", "owner/sub-project/image_1.2"),
        ("0/" + "0" * 253, "0/" + "0" * 253),
    ],
)
async def test_ghcr_tag_lookup_uses_validated_repository(image, repository):
    client = MagicMock()
    client.get = AsyncMock(
        side_effect=[
            httpx.Response(200, json={"token": "registry-test-token"}),
            httpx.Response(200, json={"tags": ["latest", "stable"]}),
        ]
    )
    with patch("api.utils.registries.httpx.AsyncClient") as factory:
        factory.return_value.__aenter__ = AsyncMock(return_value=client)
        factory.return_value.__aexit__ = AsyncMock(return_value=None)
        assert await get_image_tags("ghcr", image) == ["latest", "stable"]

    assert client.get.await_args_list[0].args == ("https://ghcr.io/token",)
    assert client.get.await_args_list[0].kwargs["params"] == {
        "service": "ghcr.io",
        "scope": f"repository:{repository}:pull",
    }
    assert client.get.await_args_list[1].args == (
        f"https://ghcr.io/v2/{repository}/tags/list?n=100",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "image",
    [
        "",
        "0",
        "0" * 255,
        "owner/" + "0" * 250,
        "/owner/image",
        "owner/",
        "owner//image",
        "owner/.image",
        "owner/../image",
        "Owner/image",
        "owner/imäge",
        "owner/image?query",
        "owner/image#fragment",
        "owner/image%2fother",
        "owner/image\n",
        "owner/image\\other",
    ],
)
async def test_invalid_ghcr_references_make_no_http_request(image):
    with patch("api.utils.registries.httpx.AsyncClient") as factory:
        assert await get_image_tags("ghcr", image) == []
    factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "image",
    ["0" * 100_000, "owner/image:" + "0" * 1024],
    ids=["oversized-slashless", "oversized-tag"],
)
async def test_oversized_ghcr_reference_is_rejected_before_url_parsing(image):
    with (
        patch("api.utils.registries.drop_registry_prefix", return_value="owner/image") as parse,
        patch("api.utils.registries.httpx.AsyncClient") as factory,
    ):
        assert await get_image_tags("ghcr", image) == []
    parse.assert_not_called()
    factory.assert_not_called()


def test_codeql_ghcr_backtracking_input_completes_in_bounded_time():
    # A subprocess timeout also catches event-loop blocking, unlike wait_for.
    script = """
import asyncio
from api.utils.registries import get_image_tags
assert asyncio.run(get_image_tags("ghcr", "0" * 100_000)) == []
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
