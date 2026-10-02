"""Regression tests for api.utils.image_inspect."""
import pytest
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

from api.utils.image_inspect import _get_dockerhub_config


@pytest.mark.asyncio
async def test_dockerhub_config_tag_is_split_before_token_request():
    """The token scope must be repository:<name>:pull, never include a tag."""
    recorded = []

    async def fake_get(url, *, headers=None, timeout=None):
        recorded.append((url, headers, timeout))
        parsed = urlsplit(url)
        assert parsed.scheme == "https"
        if parsed.hostname == "auth.docker.io" and parsed.path == "/token":
            return _FakeResponse({"token": "tok"})
        assert parsed.hostname == "registry-1.docker.io"
        if parsed.path == "/v2/library/nginx/manifests/alpine":
            return _FakeResponse({"config": {"digest": "sha256:abc"}})
        assert parsed.path == "/v2/library/nginx/blobs/sha256:abc"
        return _FakeResponse({
            "config": {
                "ExposedPorts": {"80/tcp": {}},
                "Volumes": {"/data": {}},
            },
        })

    with patch("api.utils.image_inspect.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get = fake_get
        client_cls.return_value = client

        result = await _get_dockerhub_config("nginx:alpine")

    assert result == {
        "ExposedPorts": {"80/tcp": {}},
        "Volumes": {"/data": {}},
    }

    token_url = recorded[0][0]
    assert "scope=repository:library/nginx:pull" in token_url
    assert "alpine" not in token_url

    manifest_url = recorded[1][0]
    assert manifest_url == "https://registry-1.docker.io/v2/library/nginx/manifests/alpine"


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload
