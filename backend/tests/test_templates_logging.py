"""Regression for the silent-exception finding in templates CRUD.

`init_templates_async` previously caught a network failure with
`except Exception as e: print(...)` — invisible in structured log
aggregators. Same pattern in `add_template`, `refresh_template`,
`set_template_variables`. Replaced with `logger.error/warning/info` so
errors are actually observable in production.
"""
import logging
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.db.crud import templates as crud_templates


@pytest.mark.asyncio
async def test_add_template_fetch_failure_is_logged(caplog):
    """Network failure path must hit logger.warning, not stdout."""
    caplog.set_level(logging.WARNING, logger="api.db.crud.templates")

    template = MagicMock()
    template.url = "http://example.test/feed.json"
    template.title = "Demo"

    with patch.object(crud_templates, "validate_url"), \
         patch.object(crud_templates, "_fetch_template_payload", new=AsyncMock(side_effect=OSError("net down"))):
        with pytest.raises(HTTPException) as exc:
            await crud_templates.add_template(MagicMock(), template)

    assert exc.value.status_code == 400
    assert any("Template fetch failed" in rec.message for rec in caplog.records)


def _fake_settings(url_list="LSIO|http://example.test/feed.json"):
    return lambda: type("S", (), {"DEFAULT_TEMPLATE_URLS": url_list})()


@pytest.mark.asyncio
async def test_init_templates_failure_uses_logger_exception(caplog, monkeypatch):
    """The old silent print() left operators in the dark when the default
    templates feed was unreachable; that path now produces a structured
    error log (with traceback)."""
    caplog.set_level(logging.ERROR, logger="api.db.crud.templates")
    monkeypatch.setattr("api.settings.get_settings", _fake_settings())

    fake_db = MagicMock()
    # Catalog not yet installed -> init_templates_async tries to add it.
    with patch.object(crud_templates, "get_template", new=AsyncMock(return_value=None)), \
         patch.object(crud_templates, "add_template", new=AsyncMock(side_effect=Exception("dns timeout"))):
        # init_templates_async must NOT raise (boot must continue).
        await crud_templates.init_templates_async(fake_db)

    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert error_records, "init_templates_async should log at ERROR or higher on failure"
    assert any("Failed to add default template" in r.message for r in error_records)


@pytest.mark.asyncio
async def test_init_templates_success_path_logs_info(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="api.db.crud.templates")
    monkeypatch.setattr("api.settings.get_settings", _fake_settings())
    fake_db = MagicMock()

    with patch.object(crud_templates, "get_template", new=AsyncMock(return_value=None)), \
         patch.object(crud_templates, "add_template", new=AsyncMock(return_value=MagicMock())):
        await crud_templates.init_templates_async(fake_db)

    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    assert any("Added default template" in r.message for r in info_records)


def test_no_print_calls_remain_in_module():
    """A second line of defence: scan the source for raw `print(` so a
    future patch can't quietly re-introduce stdout-only error paths."""
    import inspect

    src = inspect.getsource(crud_templates)
    # Allow `print` inside comments or string literals only if necessary —
    # the easiest sanity check is "no leading-whitespace print(" lines.
    offending = [
        line for line in src.splitlines()
        if line.lstrip().startswith("print(")
    ]
    assert not offending, f"print() reintroduced: {offending}"
