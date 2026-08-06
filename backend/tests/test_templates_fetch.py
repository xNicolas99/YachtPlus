"""Lock in the HTTP timeout for template feed downloads (BUG-003)."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api.db.crud import templates as crud


@pytest.mark.asyncio
async def test_fetch_template_payload_passes_timeout():
    fake_opener = MagicMock()
    fake_response = MagicMock()
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = False
    fake_opener.open.return_value = fake_response

    with patch.object(crud.urllib.request, "build_opener", return_value=fake_opener), \
         patch.object(crud, "json") as fake_json:
        fake_json.load.return_value = {"title": "x", "platform": "linux"}
        await crud._fetch_template_payload("http://example.test/feed.json")

    call_args = fake_opener.open.call_args
    assert call_args.kwargs.get("timeout") == crud.TEMPLATE_FETCH_TIMEOUT_S


@pytest.mark.asyncio
async def test_fetch_template_payload_rejects_unknown_extension():
    fake_opener = MagicMock()
    fake_response = MagicMock()
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = False
    fake_opener.open.return_value = fake_response

    with patch.object(crud.urllib.request, "build_opener", return_value=fake_opener):
        with pytest.raises(HTTPException) as exc:
            await crud._fetch_template_payload("http://example.test/feed.txt")

    assert exc.value.status_code == 422
    assert "Invalid filetype" in exc.value.detail


@pytest.mark.asyncio
async def test_fetch_template_payload_yaml():
    fake_opener = MagicMock()
    fake_response = MagicMock()
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = False
    fake_opener.open.return_value = fake_response

    with patch.object(crud.urllib.request, "build_opener", return_value=fake_opener), \
         patch.object(crud.yaml, "load", return_value={"k": "v"}) as fake_yaml_load:
        result = await crud._fetch_template_payload("http://example.test/feed.yaml")

    fake_yaml_load.assert_called_once()
    assert result == {"k": "v"}


def test_fetch_template_payload_timeout_constant_is_positive():
    """A 0 or negative timeout would behave like the broken default."""
    assert crud.TEMPLATE_FETCH_TIMEOUT_S > 0
