# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.0.3] - 2026-10-02 15:23 — Run R-026: Dependency-Graph-Erkennung

- Commit: dieser Commit; neue Patch-Lieferung nach dem Merge und der
  Veröffentlichung von `3.0.2`. Paket, Lockfile und `dist/version.json`
  stimmen auf `3.0.3` überein.
- Befund: Der separate [Dependency-Graph-Lauf 37011423472](https://github.com/xNicolas99/YachtPlus/actions/runs/37011423472)
  auf master konnte den `.lock`-Include aus `requirements-local.txt` nicht
  sammeln. Der [offizielle Python-Fetcher](https://github.com/dependabot/dependabot-core/blob/main/python/lib/dependabot/python/shared_file_fetcher.rb#L22)
  erkennt dafür `.txt`/`.in`-Dateien.
- Geändert: Entwicklungssperrdatei nach `requirements-dev-lock.txt`
  umbenannt; lokale Requirements, CI und Dokumentation verwenden denselben
  Dateinamen. Alle 84 Requirements behalten exakt ihre Pins, Marker und
  Hashes; `--require-hashes` bleibt verbindlich.
- Ergebnis: Hash-pip-Dry-run, 884 Backend- und 217 Frontend-Tests,
  Produktionsbuild/Bundle-Grenzen und frisches SQLite-Upgrade auf
  `20261001_0001` bestanden; Backend-Log `report/audit-r026-backend.txt`.
  Neue Pflichtchecks müssen am finalen HEAD erfolgreich sein,
  der erneute Master-Dependency-Graph-Lauf muss die Erkennung bestätigen.
- Aufgeräumt: eigene temporäre Migrationsdatenbank entfernt;
  Nachweislogs und wiederverwendbare Entwicklungsumgebung behalten.
- Ausgangsstand: [PR #260](https://github.com/xNicolas99/YachtPlus/pull/260)
  wurde als `9fdf21a` nach master gemerged. [Master-CI 37011417257](https://github.com/xNicolas99/YachtPlus/actions/runs/37011417257)
  einschließlich Publisher und [Master-CodeQL 37011417245](https://github.com/xNicolas99/YachtPlus/actions/runs/37011417245)
  einschließlich Ergebnisverarbeitung bestanden für `3.0.2`.

## [3.0.2] - 2026-10-02 14:44 — Run R-023: Schutzstack-Startfehler — verified candidate

- Commit: dieser Commit
- Version: `3.0.2`; kanonische Paket- und Lockfile-Version stimmen überein.
- Geändert: Fail2ban setzt das persistente `bans`-Verzeichnis beim Start
  ausdrücklich auf `0755`, auch bei vorhandenen Volumes und `umask 077`.
  So kann YachtPlus als UID 1000 den vom Guard UID 1001 geschriebenen Zustand
  über seinen weiterhin schreibgeschützten Mount lesen.
- Geändert: Beide Compose-Stacks geben dem Docker-Socket-Proxy ein begrenztes
  `/run`-tmpfs für die HAProxy-PID-Datei. Das Root-Dateisystem bleibt
  schreibgeschützt; Schutzstack-Regressions- und Smoke-Prüfungen erfassen die
  Dateirechte und Proxy-Bereitschaft. Startfehler liefern Health- und
  UID/GID-/Modusdiagnosen ohne Ausgabe der Container-Umgebung. Betriebs- und
  Upgradehinweise aktualisiert.
- Ergebnis: CI-Lauf [36979071014](https://github.com/xNicolas99/YachtPlus/actions/runs/36979071014)
  auf `3adb5ab` bestätigte die Startfehler des vorherigen Kandidaten: gesunder
  Guard bei für die App unlesbarem Ban-Verzeichnis und nicht schreibbare
  `/run/haproxy.pid` im Proxy. Auf dem korrigierten lokalen Kandidaten bestanden
  860 Backend-Tests, 217 Frontend-Tests, Produktionsbuild/Bundle-Grenzen und
  ein frisches SQLite-Alembic-Upgrade. `dist/version.json` enthält exakt
  `3.0.2`. Von 44
  Skriptprüfungen bestanden 43; die POSIX-Rechte-/umask-Prüfung ist auf Windows
  ausdrücklich übersprungen; der anschließende Linux-Lauf führte sie aus.
  Lokale Logs unter
  `report/audit-ci-*-r023.txt`.
- Aufgeräumt: keine zusätzlichen Wegwerf-Artefakte aus dieser Dokumentationsänderung.
- Linux-Nachweis auf `ac869d7`: [PR-Lauf 37009114081](https://github.com/xNicolas99/YachtPlus/actions/runs/37009114081)
  und [Push-Lauf 37009077607](https://github.com/xNicolas99/YachtPlus/actions/runs/37009077607)
  bestanden Image-Build, Inhalts-/Startprüfungen, Migrationen und alle 44
  Skriptprüfungen ohne Windows-Skip. Der echte Schutzstack bestätigte
  Ban/Unban, Persistenz und Ausfall/Wiederherstellung der Pflichtprotection.
  PR-Image `yachtplus:ci-smoke`, Docker-Image-ID
  `sha256:aa5fee1f0e53600f37cb48f2ac3a43d783326a0e97a543fe561495441a24efae`;
  diese lokale Image-ID ist kein veröffentlichtes Registry-Manifest-Digest.
- Freigaberegel: Die Nachkorrekturen unten gehören zu derselben Lieferung
  `3.0.2`. Merge/Publikation erfordern erfolgreiche Pflichtchecks auf dem
  tatsächlichen letzten HEAD über PR/Actions; die Nachweise sind unten belegt.

### Run R-024 — CodeQL-Nachkorrektur derselben Lieferung 3.0.2

- Commit: dieser Folgecommit; kein zusätzlicher Versionsschritt für die
  Korrektur derselben noch nicht freigegebenen Lieferung.
- Befund: [CodeQL-Analyse 37009114025](https://github.com/xNicolas99/YachtPlus/actions/runs/37009114025)
  führte Python-/JavaScript-Analyse erfolgreich aus. Der separate Results-
  Check `110844629671` schlug wegen drei High-Befunden fehl; grüne Analyze-
  Jobs reichen damit nicht für den Merge.
- Geändert: GHCR-Repositoryvalidierung mit einem linearen Parser statt
  einer für ReDoS anfälligen Regex: Referenz vor URL-Parsing auf 1024 Zeichen,
  Repository auf 255 Zeichen begrenzt, nur gültige ASCII-Segmente und keine
  HTTP-Anfrage bei ungültigem Input. Dazu exakte Host-/Pfad-/Titelvergleiche
  in den beiden gemeldeten URL-Testfixtures.
- Ergebnis: Die finale Backend-Vollsuite bestand 884 Tests einschließlich
  24 zusätzlicher Regressionen, protokolliert in
  `report/audit-ci-backend-r024-final.txt`. Die unveränderten 217 Frontend-
  Tests, Produktionsbuild/Bundle-Grenzen und Migration wurden für `3.0.2`
  bereits erfolgreich geprüft. Der damalige Linux-Skript-/Image-/Schutzstack-
  Nachweis oben galt für `ac869d7`; den Folgecommit belegt Run R-025.
- Freigabe: Erst nach erfolgreichen Pflichtchecks inklusive CodeQL-Results
  auf dem tatsächlichen letzten Commit nach `master` mergen. Der Nachweis
  auf `ac869d7` allein bestätigt den Folgecommit nicht.

### 2026-10-02 15:05 — Run R-025: Abschließende Doku derselben Lieferung 3.0.2

- Commit: dieser Doku-Folgecommit; Quellenstand
  `93fa8da2332cbd22c59f27d6871ea67828bcb17b`. Kein zusätzlicher Versionsschritt.
- Ergebnis: [PR-CI 37010339253](https://github.com/xNicolas99/YachtPlus/actions/runs/37010339253)
  und [Push-CI 37010332100](https://github.com/xNicolas99/YachtPlus/actions/runs/37010332100)
  bestanden Backend (884), Frontend (217), alle 44 Linux-Skriptprüfungen,
  Produktionsbuild/Bundle-Grenzen, Migrationen, Image-Build/Inhalts-/Startprüfung,
  Ruff und den echten Linux-Schutzstack mit Ban/Unban, Persistenz und
  Ausfall/Wiederherstellung der Pflichtprotection.
- Ergebnis: [CodeQL 37010339245](https://github.com/xNicolas99/YachtPlus/actions/runs/37010339245)
  bestand Python-/JavaScript-Analyse und Results-Check `110848620953`:
  "No new alerts", 0 Annotations. Die früheren drei High-Befunde blockieren
  diesen Quellenstand nicht mehr.
- Geändert: AGENTS und Behebungsbericht auf diese belegten Ergebnisse
  abgeglichen; historische Fehler-/Run-Nachweise erhalten.
- Aufgeräumt: temporäre Datenbank der frischen Migrationsprüfung entfernt;
  Nachweislogs und wiederverwendete Entwicklungsumgebung erhalten.
- Grenzen: Live-PostgreSQL/MySQL, Multiarch und echte Browser-/Docker-Terminal-
  Abläufe bleiben ungeprüft. Merge und Registry-Publikation werden durch die
  erfolgreichen Pflichtchecks des tatsächlichen letzten HEAD freigegeben;
  dieser Dokumentationseintrag behauptet weder einen Merge noch einen Push
  eines Registry-Manifests.

## [3.0.1] - 2026-10-02 — unreleased verification candidate

- Resolve the submitted authentication, permission, session, CSRF, TOTP,
  SMTP, template, Compose, Docker API and Vue/Vuetify correctness findings.
  Account credential versions invalidate old sessions after security changes
  and prevent tokens transferring to a recreated username. API keys are
  restricted centrally to reading data; refresh rotates and revokes sessions.
- Add migration `20261001_0001` for account credential versions, consumed
  TOTP counters, PostgreSQL timestamp types and existing SMTP encryption.
  Interrupted upgrades can resume without leaving a null credential version.
  Existing sessions and API keys must be recreated after upgrading.
- Require current passwords for account credential changes, encrypt and
  redact SMTP credentials, validate exact request origins and cookie CSRF
  proofs, and extend mutation/login audit coverage with bounded retention.
- Make Compose auto-updates opt-in, isolate subprocess credentials and
  execution, preserve valid YAML on rejected edits, support Compose v2
  filenames and stop projects before removing their files.
- Bound and pin template fetches, prevent DNS rebinding and YAML expansion,
  load async relationships eagerly, support Portainer v2 and validate
  complete settings imports before replacing catalogs.
- Correct Docker terminal/log/statistics APIs and Vue 3 controls, charts,
  theme state, session reset and refresh concurrency. Replace deprecated
  terminal packages, remove unused frontend dependencies and external fonts.
- Add universal hashed Python runtime/dev locks, Node 22 image builds,
  SHA-pinned CI actions, Compose checksum validation and SPA security headers.
  The published image uses one async worker to enforce in-memory rate limits.
- Validation before remote integration: 852 backend tests, 197 frontend
  tests and 42 release/security-script tests passed; production frontend
  build and bundle gates passed. Fresh, legacy, repeated and interrupted
  SQLite migrations passed. Final merged-tree evidence is recorded in
  `docs/AUDIT_REMEDIATION_2026-10-02.md`.
- Final merged-tree validation: 860 backend tests, 217 frontend tests,
  42 release/security-script tests, production frontend and bundle gates
  passed. The eight intervening audit-branch commits are retained in history.
- Limits: Linux Docker image/runtime and live PostgreSQL/MySQL validation
  remain unverified on this Windows host. The release claim remains open;
  CI must validate the container and mandatory fail2ban/proxy deployment.
  Publication currently targets amd64.

## [3.0.0] - 2026-09-30 — unreleased verification candidate

### Security and breaking configuration changes

- Global LAN-only default covers UI, API, setup and terminal, including
  authenticated traffic. Public access requires explicit local administrator
  confirmation and mandatory active fail2ban. The legacy public-login flag no
  longer opens access.
- Compose automatically starts real fail2ban as a capability-free, networkless
  sidecar. Persisted bans are enforced by nginx/backend; missing, stale, invalid
  or failed mandatory protection fails closed.
- nginx validates trusted HTTP proxy hops. Backend binds loopback with automatic
  forwarded rewriting disabled. App runs UID 1000 from startup, read-only with
  no capabilities; existing mounted data needs correct ownership.
- New workload profiles default to non-root, read-only rootfs, dropped
  capabilities and bounded processes. Incompatible images require explicit
  administrator approval. Saved Compose receives safe defaults; raw YAML edits
  now require an active administrator.
- Native rootless update workers use the Docker proxy, replacing direct socket
  mounts and the [archived Watchtower dependency](https://github.com/containrrr/watchtower).
  Updates preserve volumes/security/original image references and attempt
  rollback while retaining originals through startup and health checks.
- Transactional workload edits preserve originals, volumes and static networks;
  uncertain creation cleanup requires a unique transaction label. Infrastructure
  edits and proxy/guard worker updates are rejected before interruption.
- Required Linux CI security-stack checks real bans/unbans, proxy attribution,
  local/public policy, persistence and protection outage/recovery. Publication
  rejects failed, skipped or missing security validation.

### Validation and release limits

- Regression tests cover access, proxy spoofing, stale/malformed guard state,
  terminal revocation, administrator opt-in/audit failures, workload profiles,
  mount bypasses, update identity/volumes and rollback failures.
- Local unit suites, production frontend build and fresh migration results are
  recorded in the implementation report.
- This machine has no Docker/usable Linux runtime or connected browser. Actual
  image build, real fail2ban/Compose smoke, visual UI and staging upgrade checks
  remain required. Version 3.0.0 is a verification candidate, not a tested or
  published release. See `docs/SECURITY_DEPLOYMENT.md`.

## [2.0.2] - 2026-09-30

### Changed

- Consolidated GHCR publication into the CI validation run. Trusted push,
  successful jobs, unchanged commit/ref, canonical package/lock version and
  release-branch ancestry are required. Independent image publishers removed.
- Publication checks candidate contents, exact frontend version metadata and
  OCI labels, startup and Docker health before login; pushes the tested image
  ID without rebuilding and rechecks remote refs to reject stale queued runs.
- Local credentials, signing keys, salts and SQLite data are excluded from
  the Docker context; the candidate smoke test rejects packaged secret or
  runtime database files before backend initialization.
- Unified both searches with keyboard navigation and mobile access; search
  errors retain local results, show retry, cancel pending requests and reject
  outdated responses or navigation completions. Aborted navigation preserves
  the query.
- Removed whole-library Vuetify registration and deferred terminal loading
  until opening. Loading has timeout/retry/close and ignores cancelled work.
- Failed page-chunk downloads preserve the current page and offer retry or
  an explicit reload. No automatic reload discards unsaved form inputs.
- Production builds now validate asset completeness, exact version metadata,
  startup byte budgets and the lazy terminal/editor/statistics dependency graph.
  Main JavaScript shrank from 594076 to 255076 uncompressed bytes.

### Validation and limits

- 579 backend, 164 frontend and 31 publication/smoke guard tests pass, including
  malformed responses, timeout, cancelled/stale searches, duplicate actions,
  aborted navigation, failed/skipped/cancelled CI, mismatched versions/commits,
  modified checkout and moved/deleted release refs, plus packaged secret or
  database files and filesystem scan failures with empty output.
- Production frontend build and bundle gates pass: entry JS 255076 bytes,
  initial JS including static dependencies 489520 bytes, initial CSS 658530 bytes.
  Fresh and existing SQLite migrations pass in the backend suite.
- Browser checks on the production frontend cover desktop/mobile searches,
  keyboard selection with full image names, API failure, terminal load/close,
  and a real missing chunk after replacing the local build. API data is a
  local fixture; no Docker operations were performed.
- Workflow YAML and shell syntax checked. Docker image build, live health
  checks and GHCR publication remain unverified locally because no Docker
  CLI/daemon is available. Ruff remains informational; sequential registry
  pushes can leave partial tags if interrupted. No publication was performed.

## [2.0.1] - 2026-09-30

### Fixed in the interface and resource API

- Resource tables consume paginated API envelopes, load all pages, preserve
  existing data on request failures and display Docker image dates correctly.
- Resource details handle direct loading and nullable Docker metadata;
  destructive actions require confirmation and keep dialogs open on failure.
- Network creation, settings import/export and template variable editing use
  working Vue 3 form bindings; failed requests preserve user input.
- The deployment wizard uses Vuetify 3 steps and panels and sends the entered
  General, Networking, Volume, Environment and Advanced values after validation.
- Search uses Vuetify 3 bindings, preserves image namespaces and ignores stale
  responses. The sidebar can be expanded again and displays the project version.
- Log streaming calls the existing generator and forwards tail/timestamp
  options. Resource usage recognizes aiodocker container objects. Pruning uses
  supported Engine endpoints and reports failures instead of false success.
- Frontend Node engine requirements match Vite; UI version defaults to the
  canonical package version. Placeholder notification controls and Docker
  status/version claims were removed.

### Validation

- 579 backend tests and 116 frontend tests pass. The production frontend build
  succeeds; backend tests cover fresh and existing SQLite Alembic upgrades.
- Browser checks use local API fixtures for UI behavior, including API failure
  paths. No Docker CLI/daemon is available on this host; a complete container
  release build and real Docker operations remain unverified locally.

### Fixed

- First-run registration now resumes only with the original credentials and
  atomically reserves the initial administrator across concurrent workers.
- Startup applies and persists Alembic migrations before serving requests;
  local and release dependency manifests use the same supported versions.
- Login, 2FA refresh, setup navigation, mobile drawer, Vuetify 3 activators
  and resource tables now work with the current frontend stack.
- Docker resource details/deletion, image pulls with registry ports or digests,
  non-following container logs and bracketed IPv6 Host headers are handled.
- Compose examples use valid Docker socket proxy sections and the published
  image path. Release installation uses the npm lockfile without fallback.
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

- Release image health check and CI smoke tests for image contents and a
  running SPA/setup endpoint.
- Regression coverage for setup races and the complete wizard, migrations,
  Docker resource APIs, authentication and UI behavior.
- Regression tests for SMTP connection cleanup, Docker Hub image config tag
  handling, and compose delete path traversal resistance.

## Historical run log imported from the audit branch

Historical test counts and CI statements below describe those runs, not the current candidate.

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
