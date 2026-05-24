"""Regression for the "empty Templates page on fresh install" UX gap.

After running through the setup wizard, the user used to land on an
empty Templates list with no obvious way to discover the catalog
ecosystem. `mark_setup_completed` now calls `init_templates` which
installs every entry in `YACHT_DEFAULT_TEMPLATE_URLS` (default:
SelfhostedPro + Portainer Community). The seed is non-fatal: a network
failure during setup must never block /setup/finalize from succeeding.
"""
from unittest.mock import MagicMock, patch
import pytest

from api.db.crud import templates as crud_templates


def test_parse_default_template_urls_pipe_format():
    raw = "SelfhostedPro|https://example.com/a.json,Portainer|https://example.com/b.json"
    assert crud_templates._parse_default_template_urls(raw) == [
        ("SelfhostedPro", "https://example.com/a.json"),
        ("Portainer", "https://example.com/b.json"),
    ]


def test_parse_default_template_urls_skips_empty_entries():
    raw = "A|http://x,,B|http://y,"
    assert crud_templates._parse_default_template_urls(raw) == [
        ("A", "http://x"),
        ("B", "http://y"),
    ]


def test_parse_default_template_urls_bare_url_derives_title():
    out = crud_templates._parse_default_template_urls("https://raw.githubusercontent.com/x/y/z.json")
    assert len(out) == 1
    title, url = out[0]
    assert "raw.githubusercontent.com" in title
    assert url == "https://raw.githubusercontent.com/x/y/z.json"


def test_parse_default_template_urls_empty_returns_empty():
    assert crud_templates._parse_default_template_urls("") == []
    assert crud_templates._parse_default_template_urls(None) == []


def test_init_templates_seeds_when_empty(monkeypatch):
    """Fresh install (no templates in DB) -> add_template called for each
    configured catalog URL."""
    monkeypatch.setattr(
        "api.settings.get_settings",
        lambda: type("S", (), {
            "DEFAULT_TEMPLATE_URLS": "SH|http://a,PT|http://b",
        })(),
    )

    db = MagicMock()
    with patch.object(crud_templates, "get_template", return_value=None) as get_t, \
         patch.object(crud_templates, "add_template") as add_t:
        crud_templates.init_templates(db)

    assert get_t.call_count == 2
    assert add_t.call_count == 2
    added_titles = [call.args[1].title for call in add_t.call_args_list]
    assert "SH" in added_titles and "PT" in added_titles


def test_init_templates_skips_already_installed(monkeypatch):
    monkeypatch.setattr(
        "api.settings.get_settings",
        lambda: type("S", (), {
            "DEFAULT_TEMPLATE_URLS": "SH|http://a,PT|http://b",
        })(),
    )

    db = MagicMock()
    # First catalog already exists; second isn't installed yet.
    def fake_get(db, url):
        return MagicMock() if url == "http://a" else None
    with patch.object(crud_templates, "get_template", side_effect=fake_get), \
         patch.object(crud_templates, "add_template") as add_t:
        crud_templates.init_templates(db)

    assert add_t.call_count == 1
    assert add_t.call_args.args[1].url == "http://b"


def test_init_templates_swallows_network_failure(monkeypatch, caplog):
    """A failed fetch on ONE catalog must not block the OTHER catalog,
    and must not raise out of init_templates (would block /finalize)."""
    monkeypatch.setattr(
        "api.settings.get_settings",
        lambda: type("S", (), {
            "DEFAULT_TEMPLATE_URLS": "BAD|http://broken,GOOD|http://works",
        })(),
    )

    db = MagicMock()

    def fake_add(_db, template):
        if "broken" in template.url:
            raise OSError("network down")
        return template

    with patch.object(crud_templates, "get_template", return_value=None), \
         patch.object(crud_templates, "add_template", side_effect=fake_add) as add_t, \
         caplog.at_level("ERROR"):
        # Must NOT raise.
        crud_templates.init_templates(db)

    # Both URLs attempted; the good one succeeded.
    assert add_t.call_count == 2
    # Failure logged with traceback so operators can see it.
    assert any("broken" in rec.message or "Failed" in rec.message for rec in caplog.records)


def test_init_templates_noop_when_url_list_empty(monkeypatch):
    """`YACHT_DEFAULT_TEMPLATE_URLS=""` opt-out path."""
    monkeypatch.setattr(
        "api.settings.get_settings",
        lambda: type("S", (), {"DEFAULT_TEMPLATE_URLS": ""})(),
    )
    db = MagicMock()
    with patch.object(crud_templates, "add_template") as add_t:
        crud_templates.init_templates(db)
    add_t.assert_not_called()


def test_mark_setup_completed_calls_init_templates(monkeypatch, tmp_path):
    """End-to-end: finalize-setup -> seed runs. Network failure inside
    seed must not bubble out (finalize must succeed regardless)."""
    import api.routers.setup.setup as setup_mod

    # Redirect the flag-file write into tmp_path so the test doesn't
    # touch /config (and doesn't leak into other tests via the module's
    # cached SETUP_FLAG_FILE constant).
    monkeypatch.setattr(setup_mod, "SETUP_FLAG_FILE", str(tmp_path / ".flag"))

    db = MagicMock()
    db.query.return_value.first.return_value = None

    with patch("api.db.crud.templates.init_templates", side_effect=OSError("net down")) as init:
        # Must not raise — finalize will call this and we can't let a
        # transient catalog fetch failure block the user out of setup.
        setup_mod.mark_setup_completed(db)
    init.assert_called_once_with(db)
