# Changelog

## 2026-09-10 13:08 — Code-Analyse (2 Subagenten, DeepSeek 4.1 Flash) + Verifikation
- Geändert: AGENTS.md (neuer Abschnitt 18 "Offene Audit-Befunde" mit 10 High, 14 Medium, 4 Low sowie 9 widerlegten Falschmeldungen)
- Ergebnis: 28 verifizierte Befunde dokumentiert; 9 Subagenten-Behauptungen als falsch eingestuft und dokumentiert. Keine Produktivdatei verändert. Analyse rein lesend.
- Aufgeräumt: nichts (keine Artefakte erzeugt)
- Offen: venv/ und frontend/node_modules/ fehlen — vor Fix-Verifikation neu errichten.


All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `api/routers/smtp.py`: SMTP test connection is now closed on the error path
  and uses a 10-second timeout, preventing socket leaks when `sendmail()` fails
  (`_send_test_email_sync`).
- `api/routers/smtp.py`: Replaced deprecated Pydantic `.dict()` calls with
  `.model_dump()` in `update_smtp_settings`, removing Pydantic V3 deprecation
  warnings.
- `api/actions/compose.py`: `_delete_compose_sync` now resolves the project path
  with `pathlib` and validates it stays inside `COMPOSE_DIR`, fixing broken path
  handling when `COMPOSE_DIR` lacks a trailing slash and hardening traversal
  resistance.
- `api/utils/image_inspect.py`: `_get_dockerhub_config` strips the image tag
  before requesting the Docker Hub token, fixing config inspection for tagged
  images (e.g. `nginx:alpine`) where the token scope previously included the
  tag and was rejected.

### Added

- Regression tests for SMTP connection cleanup, Docker Hub image config tag
  handling, and compose delete path traversal resistance.
