# Changelog

## 2026-09-10 14:25 — Run R-021: Doku-Sync — Run-Protokoll und CHANGELOG-Pflichtregel
- Commit: dieser Doku-Sync-Commit
- Geändert: `AGENTS.md` (neue Pflichtregel Doku-Sync, Run-Protokoll mit R-001 bis R-021, Abschnitt 18 auf behoben in R-020 gesetzt, neuer Abschnitt 18.6, Test-Baseline von 513 auf 543); `CHANGELOG.md` (Run-Einträge R-012 bis R-021)
- Ergebnis: rein dokumentarisch, keine Codeänderung; Teststand unverändert 543 Backend und 21 Frontend
- Aufgeräumt: keine Artefakte
- Offen: M13 (Vuetify-3-Migration der v-list-item-Elemente)

## 2026-09-10 14:21 — Run R-020: Audit-Befunde Abschnitt 18 behoben (Backend und Frontend)
- Commit: aed5e1f
- Geändert: `backend/api` (`db/database.py`, `db/crud/settings.py`, `db/crud/users.py`, `db/schemas/users.py`, `routers/smtp.py`, `routers/containers.py`, `routers/setup/setup.py`, `auth/auth.py`, `utils/registries.py`, `actions/apps.py`) und `backend/tests`; `frontend/src` (`main.js`, `views/Home.vue`, `store/modules/volumes.js`, `store/modules/templates.js` sowie 21 Komponenten)
- Ergebnis: 543 Backend-Tests bestanden, 21 Frontend-Tests bestanden, Vite-Build erfolgreich, beide GitHub-Workflows grün
- Aufgeräumt: `backend` `__pycache__` und `.pytest_cache`, `frontend` `dist` und `node_modules/.cache`

## 2026-09-10 13:08 — Code-Analyse (2 Subagenten, DeepSeek 4.1 Flash) + Verifikation
- Geändert: AGENTS.md (neuer Abschnitt 18 "Offene Audit-Befunde" mit 10 High, 14 Medium, 4 Low sowie 9 widerlegten Falschmeldungen)
- Ergebnis: 28 verifizierte Befunde dokumentiert; 9 Subagenten-Behauptungen als falsch eingestuft und dokumentiert. Keine Produktivdatei verändert. Analyse rein lesend.
- Aufgeräumt: nichts (keine Artefakte erzeugt)
- Offen: venv/ und frontend/node_modules/ fehlen — vor Fix-Verifikation neu errichten.

## 2026-09-08 10:56 — Run R-019: Kosmetik-Rest-Batch
- Commit: 5924edc
- Geändert: `frontend/src` (F72 Race-Guard in RegistryBrowser; Vuetify-3-Props in ContainerTerminal, ContainerLogs, Prune, ServerUpdate, ServerSettings und Setup; Sidebar-Version dynamisch; `notifications.js`; TemplatesDetails; `vite.config.js`) und `backend/api` (B30 WS-Close-Frame und Docker-None-Guard, B23 Doku)
- Ergebnis: 539 Backend-Tests und 21 Frontend-Tests bestanden, Vite-Build erfolgreich
- Aufgeräumt: `frontend/dist` und `node_modules/.cache`

## 2026-09-08 09:48 — Run R-018: Self-Restart repariert
- Commit: 55636b8
- Geändert: `backend/api/actions/apps.py` (Self-Restart über neuen Helfer mit eigenem aiodocker-Client) und `backend/tests/test_self_restart.py` (neu, drei Tests)
- Ergebnis: 539 Backend-Tests bestanden
- Aufgeräumt: `__pycache__` und `.pytest_cache`

## 2026-09-08 09:13 — Run R-017: Rest-Batch Frontend und Backend
- Commit: 84d5f09
- Geändert: `frontend` (F16 vee-validate v4 in ServerInfo, F34 und F35 Slash-Normalisierung, F36, F39, F56, F68, F69, F73, F77) und `backend` (B26 Commit-Rollback, B27 Lockfile 0o600, B28 kein Port-Echo)
- Ergebnis: 536 Backend-Tests und 21 Frontend-Tests bestanden, Vite-Build erfolgreich
- Aufgeräumt: `__pycache__`, `.pytest_cache` und `dist`

## 2026-09-08 09:00 — Run R-016: Nachzügler Security und UX
- Commit: 627fe0d
- Geändert: `backend/api/routers/users.py` (B22 Last-Admin-Gate beim Update) und `frontend/src` (F33 Port-Links protokollbewusst, F71 rel noopener)
- Ergebnis: 536 Backend-Tests und 21 Frontend-Tests bestanden, Vite-Build erfolgreich
- Aufgeräumt: `__pycache__`, `.pytest_cache` und `dist`

## 2026-09-07 15:41 — Run R-015: TOTP-Fenstertoleranz (CI)
- Commit: 41a4750
- Geändert: `backend/api/routers/auth_2fa.py` (valid_window gleich 1 an beiden TOTP-Verifikationen)
- Ergebnis: 9 Tests in test_auth_2fa bestanden, CI-Lauf auf 41a4750 grün
- Aufgeräumt: keine Artefakte

## 2026-09-07 15:39 — Run R-014: Subagenten-Bug-Batch und Audit-Doku
- Commit: e5214b6
- Geändert: `backend/api` (B1 bis B24, unter anderem API-Key-Gates, perm_restart, selectinload, Route-Ordering, SMTP-Schema und Timeout, prune über API, Cache-Bound, auth_check, Import-Whitelist, Last-Admin); `frontend/src` (F1 bis F78, unter anderem setApp, v-window, display-Breakpoints, Login-2FA, snackbar, env-split, Guards); `AGENTS.md` (neuer Abschnitt 18)
- Ergebnis: 536 Backend-Tests und 21 Frontend-Tests bestanden, Vite-Build erfolgreich
- Aufgeräumt: `__pycache__`, `.pytest_cache` und `dist`

## 2026-09-03 10:37 — Run R-013: Dockerfile-Build-Fix
- Commit: 7e1808c
- Geändert: `Dockerfile` (COPY der Wheels und der `requirements.txt` vor `pip install`)
- Ergebnis: Docker-Image-CI und CI-Tests/Build wieder grün
- Aufgeräumt: keine Artefakte

## 2026-09-03 10:29 — Run R-012: Security-Fixes P0/P1 und P2
- Commit: 4f8a063
- Geändert: `backend/api` (Self-Privilege-Escalation über auth/me, stats-KeyError, pause und unpause Gate, GET apps name, print durch logger ersetzt, GET zu POST beim pull, Rate-Limit, pool_pre_ping, Pagination) und `frontend/src` (calculated zu computed, snackbar, Login-Auth, api-Präfix, EventSource-URLs, finally- und catch-Fixes, Port-Links, Barrierefreiheit)
- Ergebnis: Backend- und Frontend-Suiten bestanden
- Aufgeräumt: `__pycache__`, `.pytest_cache` und `dist`

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
