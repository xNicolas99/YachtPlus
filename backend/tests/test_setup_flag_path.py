"""Regression for BUG-013/015: SETUP_FLAG_FILE was lifted straight from
the environment with no path validation, and the file-write path used a
bare `except: pass` that swallowed every failure silently.

The fix resolves the env value against a whitelist of allowed roots
(/config, /tmp, $cwd) and falls back to the default when it doesn't
match; the write path now logs failures at WARNING so a wedged disk
is at least visible in `journalctl`.
"""
import importlib
import os
import pytest


def _reload_setup_module(monkeypatch, flag_value):
    if flag_value is None:
        monkeypatch.delenv("SETUP_FLAG_FILE", raising=False)
    else:
        monkeypatch.setenv("SETUP_FLAG_FILE", flag_value)
    import api.routers.setup.setup as setup_mod
    importlib.reload(setup_mod)
    return setup_mod


def test_default_used_when_env_missing(monkeypatch):
    mod = _reload_setup_module(monkeypatch, None)
    # On Linux the default is /config/.setup_completed; on Windows the
    # path string is the same literal but os.path.abspath turns it into
    # D:\config\.setup_completed. Both are correct — what we're asserting
    # is "did the resolver use the configured default, not the env value".
    assert mod.SETUP_FLAG_FILE.replace("\\", "/").endswith("/config/.setup_completed")


def test_resolver_accepts_path_under_cwd(monkeypatch):
    candidate = os.path.join(os.getcwd(), "_test_flag")
    mod = _reload_setup_module(monkeypatch, candidate)
    assert mod.SETUP_FLAG_FILE == os.path.abspath(candidate)


def test_resolver_rejects_traversal_outside_allowed_roots(monkeypatch):
    """A SETUP_FLAG_FILE in /etc/passwd (or anywhere else outside the
    allow-list) must be ignored — the resolver falls back to the default.
    """
    mod = _reload_setup_module(monkeypatch, "/etc/passwd")
    assert mod.SETUP_FLAG_FILE == "/config/.setup_completed"


def test_mark_setup_completed_logs_write_failure(monkeypatch, caplog):
    """A failure to write the legacy flag file must surface in the log
    (it used to be swallowed silently by `except: pass`).
    """
    mod = _reload_setup_module(monkeypatch, None)
    from unittest.mock import AsyncMock, MagicMock, patch

    db = AsyncMock()
    # mark_setup_completed is async and calls await db.execute(select(...)).
    db.execute = AsyncMock(return_value=MagicMock())
    db.execute.return_value.scalars.return_value.first.return_value = None
    db.commit = AsyncMock()
    db.add = MagicMock()

    with patch.object(mod.os, "makedirs", side_effect=Exception("read-only")), \
         caplog.at_level("WARNING", logger=mod.logger.name):
        import asyncio
        asyncio.run(mod.mark_setup_completed(db))

    assert any("SETUP_FLAG_FILE" in record.message for record in caplog.records)
