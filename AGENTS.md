# AGENTS.md — orientation for coding agents

Final merged audit candidate (2026-10-02): **860 backend + 217 frontend +
42 release/security-script tests passed**, plus production frontend/bundle
gates and SQLite migration regressions. Docker/Linux verification remains
open. See [the remediation report](docs/AUDIT_REMEDIATION_2026-10-02.md).
`frontend/src/utils/containerLinks.js` centralizes browser-origin-aware,
IPv6-safe port URLs; settings tabs synchronize with child-route deep links.

This file is for any AI agent (Claude, Codex, Jules, Cursor, etc.) opening this
repository. It explains *how the system works* so you can ship a change without
breaking it, not what was found during some past audit.

Always verify a claim here against the current code (`rg`/`grep`) before relying
on it. If you find a mismatch, fix the code OR fix this file — don't perpetuate
the lie.

> **Hard rule — keep this file in sync with the repo.**
> Any change that touches the *structure* of the project — new directory,
> renamed module, new router/middleware, new env var, new external integration,
> changed convention, new high-risk surface, modified auth flow, dropped or
> added dependency — **must** be reflected in AGENTS.md in the same commit /
> PR that introduces it. If you don't, the next agent reads stale guidance
> and breaks things. Updating AGENTS.md is part of the change, not an
> afterthought.

---

## Doku-Sync — PFLICHT bei JEDEM Durchlauf (Run)

- Ein Run ohne Doku-Eintrag gilt als nicht abgeschlossen, auch wenn der Code funktioniert.
- **Definition Run:** eine abgeschlossene Arbeitseinheit mit eigenem Commit, also Implementierung, Bugfix, Refactoring, Analyse, Build- oder Testlauf oder Doku-Änderung.
- **Pflichtschritte am Ende jedes Runs in dieser Reihenfolge:**
  1. Verifizieren durch die vorgeschriebenen Tests/Build-/Migrationsprüfungen mit echtem belegtem Ergebnis, ohne erfundene Zahlen.
  2. Nicht mehr benötigte eigene Caches und Wegwerf-Artefakte aufräumen; benötigte Prüfnachweise und wiederverwendete Entwicklungsumgebungen erhalten.
  3. `CHANGELOG.md` fortschreiben, neueste Lieferungen zuerst, alte Einträge nie kürzen. Neue datierte Lieferungen erfordern den Versionsschritt und die Belege aus Abschnitt 16; die Run-Regel ist keine Ausnahme davon. Eine Korrektur derselben Lieferung ergänzt deren bestehenden Eintrag.
  4. `AGENTS.md` aktualisieren, wenn sich Baseline, Struktur, Routen, Pfade, Konventionen, Env-Variablen oder Risikoflächen geändert haben.
  5. Run-Protokoll ergänzen, also eine Zeile in der Tabelle Run-Protokoll am Dateiende.
  6. Commit nur der fachlich geänderten Dateien, und kein `git add -A`, wenn fremde Änderungen im Arbeitsverzeichnis liegen.
  7. Im autorisierten Umfang pushen und danach prüfen, dass Remote-Hash und lokaler HEAD übereinstimmen.

Format eines `CHANGELOG.md`-Eintrags:

```
## JJJJ-MM-TT HH:MM — Run R-0NN: kurze Bezeichnung
- Commit: <kurz-hash>
- Version: <MAJOR.MINOR.PATCH; gleiche kanonische Version in package.json und Lockfile>
- Geändert: <Dateien/Themen>
- Ergebnis: <Tests/Build mit belegten Zahlen>
- Aufgeräumt: <Caches/Artefakte>
- Offen: <optional>
```

**Verboten:** erfundene Testzahlen, Prosa-Romane, Umsortieren alter Einträge, Doku-Änderung ohne zugehörigen Run-Eintrag.

---

## 1. What this repo is

YachtPlus is a self-hosted container management UI for Docker / Docker Compose,
shipped as a single Docker image. Frontend (Vue 3 SPA) and backend (FastAPI)
are built into one container; nginx routes traffic.

The repo is a monorepo with two packages: `frontend/` and `backend/`. No
monorepo tooling — they are independent Node and Python projects.

---

## 2. Stack at a glance

| Layer | Tech |
|---|---|
| Frontend | Vue 3.4 + Vite 7 + Vuetify 3, Vuex 4 for state, vue-router 4, vee-validate v4, axios. Routes are lazy-loaded (code-split); vendor libs split via `manualChunks` in `vite.config.js`. |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.x (async engine), aiodocker, APScheduler, slowapi (rate limit), bcrypt, PyJWT, pyotp |
| DB | SQLite default (`sqlite:////config/yacht.db`, via `sqlite+aiosqlite`); Postgres via `postgresql+asyncpg`; MySQL via `mysql+aiomysql` — all driven by `DATABASE_URL` |
| Build/Deploy | Multi-stage `Dockerfile` (Node build → Python deps build → Python runtime + nginx) with `/api/setup/status` health check; `docker-compose.yml`; `.github/workflows/ci.yml` validates and publishes. Publication depends on successful validation in the same run, plus candidate smoke/start/health checks. Ruff is informational. |
| Test | pytest (backend), vitest (frontend) | Backend and frontend tests are **tracked** in this repo (`backend/tests/`, `frontend/**/*.test.js`). CI runs both suites. |

---

## 3. Layout (read this before adding files)

```
backend/
  start.sh                 # UID 1000-only entrypoint: validate writable mounts, supervise gunicorn+nginx
  configure_nginx.py       # Validates HTTP proxy CIDRs and writes runtime nginx includes
  api/
    main.py                # FastAPI app, middleware stack, router includes
    settings.py            # Pydantic settings + SECRET_KEY bootstrap (fail-fast)
    auth/
      jwt.py               # create_access_token, AuthWrapper, cookie helpers
      auth.py              # auth_check / auth_check_setup_pending / check_permission
    routers/               # One file per feature → FastAPI APIRouter
      apps.py compose.py containers.py dashboard.py templates.py
      users.py auth_2fa.py registries.py resources.py smtp.py search.py
      watchtower.py audit.py app_settings.py
      setup/setup.py
    actions/               # Business logic, mostly async wrappers around aiodocker / subprocess
    db/
      models/              # SQLAlchemy ORM models
      schemas/             # Pydantic request/response shapes
      crud/                # Pure DB ops (no FastAPI in here)
    services/              # Leader-elected retention cleanup; opt-in Compose updates
    utils/                 # CSRF/audit ASGI middleware, secret files, SMTP, bounded YAML, Docker helpers
  alembic/                 # Migrations
  tests/                   # pytest, with conftest.py for env setup (tracked; run in CI)
  alembic/versions/        # tracked Alembic migrations; run `alembic upgrade head` for upgrades
  requirements.txt         # Runtime dependency input, excludes test tools
  requirements.lock        # Exact runtime versions with distribution hashes
  requirements-dev.txt     # Runtime inputs plus pytest tooling
  requirements-dev.lock    # Hashed development resolution constrained by runtime lock
frontend/
  src/
    main.js                # App bootstrap; DOMPurify allowlist; axios interceptor + 401 → refresh
    App.vue
    router/index.js        # vue-router 4, navigation guards (setup + auth)
    store/                 # Vuex 4 modules: auth, apps, projects, snackbar, templates, networks, …
    plugins/vueutils.js    # $formatDate / $timeAgo / $truncate (dayjs)
    plugins/vuetify.js
    views/                 # Page-level components, one per route
      auth/Login.vue       # Cookie-based login + 2FA flow
      auth/Setup.vue       # First-run wizard
    components/            # Reusable UI: applications/, compose/, charts/, auth/, nav/, …
    utils/                 # JS helpers + specs; resourcePages.js loads paginated resource API results
  vite.config.js
  scripts/check-bundle.mjs  # Manifest/asset, initial size and lazy-feature build gates (+ Vitest tests)
  package.json
scripts/
  security-stack-smoke.py  # Mandatory Linux Docker/Compose protection runtime gate
  release_gate.py          # Fail-closed GHCR publication policy (+ test_release_gate.py)
  push-to-github.sh        # Push local work to GitHub with a PAT (see scripts/README.md)
  README.md
Dockerfile
docker-compose.yml         # Protected production stack with mandatory fail2ban
docker-compose.example.yml # Hardened example using a docker-socket-proxy
nginx.conf
fail2ban/                  # UID 1001 sidecar: real jail/filter, state action, supervised readiness
docs/                      # User-facing how-tos (reverse proxy, …)
DEBUGGING_CHEATSHEET.md
README.md                  # End-user facing; keep in sync with reality
```

**Co-location rule:** a feature usually has parallel files at the same name
across layers — e.g. `routers/apps.py` calls `actions/apps.py` which uses
`db/crud/apps.py` (where applicable) plus `db/schemas/apps.py` and
`db/models/users.py`. When you add a feature, mirror that pattern.

---

## 4. Request lifecycle (backend)

```
Browser ── HTTPS ──► nginx (port 8080)
                        │
                        ├─► /api/*  ─► gunicorn ─► FastAPI app (api.main:app)
                        │                              │
                        │   Middleware chain (top→down):
                        │     1. AccessPolicyMiddleware → global HTTP/WS policy
                        │     2. CSRFProtectionMiddleware → origin + cookie proof
                        │     3. MutationAuditMiddleware → successful mutations
                        │     4. add_security_headers → CSP, etc.
                        │     5. _trusted_host_middleware → settings.ALLOWED_HOSTS
                        │     6. CORSMiddleware → settings.CORS_ORIGINS
                        │     7. check_setup_status → 428 until setup finalized
                        │     8. SlowAPIMiddleware → rate limits
                        │                              │
                        │                              ▼
                        │   Router → Endpoint
                        │     - Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
                        │     - await auth_check(Authorize)              # data routes
                        │       OR await auth_check_setup_pending(Authorize, db)  # setup/2FA
                        │     - await check_permission("perm_x", Authorize, db)  # fine-grained
                        │     - business call → actions/* or db/crud/*
                        │
                        └─► /     ─► static SPA (frontend/dist via nginx)
```

Same-origin model: SPA and API share the host, so the HttpOnly auth cookie
flows automatically. The frontend never sees the raw JWT.

**Async model:** the whole backend is async. `api.db.database.SessionLocal` is
an `async_sessionmaker` (AsyncSession). All CRUD + router handlers are
`async def` and use `await db.execute(select(...))`. Blocking I/O (SMTP,
psutil, subprocess, template fetches, sync Docker SDK) is isolated via
`asyncio.to_thread` / `run_in_thread`. The app's DDL runs in the `lifespan`
hook via `await engine.run_sync(Base.metadata.create_all)` — never sync
`Base.metadata.create_all(bind=engine)` (would crash on the AsyncEngine).

---

## 5. Auth model (the part you must not break)

- **Token:** JWT (HS256) signed with `settings.SECRET_KEY`. Lives in
  HttpOnly cookie `access_token_cookie`, SameSite=lax. Cookie `Secure` is
  inferred per request from HTTPS (including nginx's trusted forwarded
  scheme), unless `SECURE_COOKIES` explicitly overrides it. `ENVIRONMENT`
  alone does not force `Secure`, so LAN HTTP setup remains usable.
- **Claims:** `sub` (username), `exp`, `jti` and `av` (the account's random
  `auth_version`); optional `setup_pending: bool` and `type: api_key`.
  Every authenticated request checks the account's current version and
  active state. Password/username, administrative permission and 2FA changes
  rotate the version; deleted and recreated usernames cannot inherit old
  sessions. The credential migration invalidates tokens without `av`.
- **CSRF:** a separate readable `csrf_access_token` cookie carries a random
  proof, never the JWT. Cookie-authenticated mutations require the matching
  `X-CSRF-TOKEN` header. Login and registration do not require that proof;
  unsafe browser requests still require an exact matching Origin. Bearer
  clients use their explicit credential. WebSocket Host/Origin is checked
  before the terminal handler, including scheme and port.
- **Two cookie-issuing endpoints:**
  - `POST /api/auth/login_cookie` — normal login, validates password + TOTP
    if 2FA enabled.
  - `POST /api/setup/register` — first-time admin registration. Issues a
    *15-minute* token with `setup_pending=True`. Body returns only
    `{login, username}`, **never** the raw token.
    While setup is pending, only the original username with its existing
    password can resume registration. The first account is claimed atomically
    across workers through `setup_registration_claim`.
- **Refresh:** the shared frontend refresh promise coalesces concurrent 401s
  and periodic refreshes → POST `/api/auth/refresh` with CSRF proof → retry.
  A refresh blacklists the old JTI before issuing its replacement; repeated
  use of the same token fails. Blacklist/account DB failures fail closed.
- **API keys:** `type=api_key` allows only GET/HEAD data routes and excludes
  `/api/auth`. Existing user permissions still apply. Keys cannot refresh,
  manage accounts, mutate Docker/Compose/settings, or open a terminal. The
  DB stores the JTI, expiry and its SHA-256 hex digest (64 characters), not
  the bearer token; creation returns the bearer token once.
- **Sensitive account changes:** self-service username/password changes
  require `current_password` and use a schema that cannot set permissions.
  User create/edit persists every action permission, including restart.
  Admin edits/deletions lock the active-admin set and preserve at least one
  active superuser; an administrator cannot deactivate/demote their own account.
- **TOTP:** generate is POST-only and refuses an already enabled secret.
  `utils/totp.py` verifies the adjacent time-step window and atomically
  consumes the matched `otp_last_step`, so a successful code cannot be
  replayed across login/setup/2FA, adjacent windows or workers.

### Two defense layers, both must stay intact

1. **Middleware** (`backend/api/main.py`, `check_setup_status`): returns
   `428 Precondition Required` on any `/api/*` route except `/api/auth`
   and `/api/setup` until `is_setup_completed(db) == True`.
2. **`auth_check`** (`backend/api/auth/auth.py`): rejects tokens with
   `setup_pending=True` (403). Used by every data router.
   **`auth_check_setup_pending`** allows them — but *only while setup is
   not yet finalized* (stale-token block).

### /refresh validates the underlying account

`POST /api/auth/refresh` checks the account, credential version and blacklist,
as every normal authenticated request does. A deactivated or changed account
cannot continue using its previous token before expiry. Refresh additionally
requires revoking the current JTI exactly once. The SPA clears its account
state and returns to login when refresh fails.

### When you add a new endpoint

- **Public** (login, status, healthcheck): no auth dep. Add to the middleware
  whitelist if needed.
- **Setup-time** (2FA generate/enable, finalize): use
  `await auth_check_setup_pending(Authorize, db)`.
- **Normal data routes:** call `await auth_check(Authorize)` first thing in the
  handler. Optionally follow with `await check_permission("perm_x", Authorize, db)`
  for non-superuser access control.

> **Note:** since the async migration, `auth_check`, `auth_check_setup_pending`,
> `check_permission`, `require_superuser`, `Authorize.jwt_required()` and
> `Authorize.get_jwt_subject()` are all **async** and must be awaited. Never
> call them without `await` from an `async def` handler.

### User model permissions (in `db/models/users.py`)

Flat boolean flags on `User`: `is_superuser`, `is_active`, `is_2fa_enabled`,
and granular `perm_start`, `perm_stop`, `perm_restart`, `perm_delete`.
Superusers bypass `check_permission`.

> **No `perm_read`.** There is intentionally no dedicated read-only
> permission. Read endpoints that expose container state, configuration, or
> compose projects are gated behind `perm_start` (the lowest operator
> permission) because even read access to a container orchestrator leaks
> env vars, secrets, and runtime state that can be abused for privilege
> escalation. A future `perm_read` would require its own audit/scope work;
> until then, treat `perm_start` as the read floor. (FND-103 / S10)

### Where each permission is enforced

| Endpoint family | Gate |
|---|---|
| `/api/apps/actions/{name}/{action}` | `auth_check` + `check_permission("perm_{start,stop,restart,delete}")` based on the action |
| `/api/apps/{name}/logs`, `/processes` | `auth_check` + `perm_start` — log lines often contain secrets, processes leak cmdlines |
| `/api/apps/{name}/support` | superuser only — bundles env + inspect output |
| `/api/compose/{project}/actions/{action}` | `auth_check` + permission mapped via `_ACTION_PERMISSIONS` (same gates as apps router) |
| `/api/compose/{project}/edit` | Active superuser only; raw YAML can explicitly opt into image compatibility. Path/body project names must match. |
| `/api/compose/{project}/support` | superuser only |
| `/api/templates` POST / DELETE / `/refresh` | superuser only via local `_require_superuser` helper (mutates the shared library + outbound URL fetch) |
| `/api/containers/{id}/*` lifecycle (start/stop/restart/delete) | `auth_check` + perm + **API keys rejected** (FND-205) — same policy as apps router |
| `/api/containers/{id}/exec` (WS) | shell-name whitelist → JWT decode → reject `setup_pending` → DB lookup (`is_active`) → `perm_start`. See section 5 below for the WS-specific contract. |
| `/api/auth/users/{user_id}` DELETE / account edits | active superuser only; serialized guard preserves at least one active admin and refuses self-delete/deactivation/demotion |
| `/api/settings/email` GET / POST / `/test` | active superuser only; response omits the password and reports `password_configured` |
| `/api/auth/api/keys/{id}` DELETE | owner OR superuser; non-owner gets the same "Key not found" payload as a missing id (no IDOR id-existence leak) |

### `/api/containers/{id}/exec` WebSocket contract

1. Outer access-policy and CSRF middleware validate protection state, Host
   and exact Origin before the handler. A foreign browser origin closes 1008.
2. `await websocket.accept()` — required to receive a `send_json`/`close` frame.
3. **Shell-name whitelist** (`containers.py::ALLOWED_EXEC_SHELLS`). Anything
   else gets a `{"error": "Forbidden: shell not allowed"}` and a 1008 close
   *before* any auth check, so token-probing attempts get no signal.
4. Cookie-only JWT (`access_token_cookie`); URL/query and Bearer tokens are
   never accepted. Reject API keys and setup-pending tokens.
5. Validate JTI revocation, account `av`, active state and `perm_start`
   (superusers bypass). Record actor/container/shell, without terminal bytes.
6. Use aiodocker's `DockerExec.start(detach=False)` stream with byte input
   and bounded resize messages. A periodic guard ends expired/revoked sessions
   and account/permission changes; disconnect cancels the peer task and closes
   the stream/client. The outer gate also rechecks protection on input frames.

Terminal IN/OUT bytes are deliberately not logged — they include passwords
typed at sudo prompts, tokens echoed by tools, file contents dumped by
`cat`. The debug log captures frame length only.

---

## 6. Security defaults (don't loosen without thinking)

### Global access and mandatory protection contract

- `utils/access_policy.py` installs the **outermost pure ASGI** gate for HTTP
  and WebSockets, including setup, preflight and authenticated traffic. Existing
  terminal frames recheck policy and protection. nginx uses the same decision
  via an internal `auth_request` for static assets and API/WS handshakes.
- `/internal/access` responds only to loopback trusted peers supplying a valid
  normalized `X-Real-IP`; nginx denies the external path. Gunicorn binds only
  `127.0.0.1:8000`. Uvicorn/Gunicorn forwarded-header rewriting is disabled so
  the gate can verify the actual peer itself.
- Missing access policy means LAN-only: loopback, RFC1918 IPv4 and IPv6 ULA.
  Public access is a persisted explicit opt-in, not a legacy environment flag.
  Admin GET/PUT `/api/settings/security` reports required/active fail2ban and
  local modification permission. PUT requires an active superuser and local
  source; public enable also requires confirmation, mandatory protection and
  fresh readiness. A durable `security.network_access.requested` audit entry
  precedes mutation. `components/settings/NetworkAccessSecurity.vue` displays
  last-confirmed policy separately from drafts and handles ambiguous failures.
- `YACHT_ACCESS_POLICY_FILE` defaults to `/config/access-policy.json` (atomic
  replacement, mode 0600). `YACHT_FAIL2BAN_REQUIRED` defaults false for standalone
  local development but true in both Compose files. Public sources cannot
  use a persisted public opt-in after mandatory protection is disabled.
- `YACHT_FAIL2BAN_STATE_DIR` defaults `/run/yachtplus-security`; app mounts it
  read-only. Sidecar UID 1001 writes atomic `ready.json` with numeric timestamp
  and `status: ready`, refreshed every 5 seconds only after validating real jail,
  action and active bans; age over 30 seconds or invalid state fails closed.
  `bans/<canonical-IP-with-colons-replaced-by-underscores>.json` stores finite
  `expires_at`; IPv4-mapped IPv6 normalizes to IPv4. A ban blocks all HTTP/WS.
- `YACHT_SECURITY_LOG` defaults `/config/security/auth.log`: one atomic append
  per failed login, UTC timestamp + `yachtplus-auth failure ip=<canonical-IP>`.
  No username, password or arbitrary reason enters the fail2ban filter. Log
  failure with required protection rejects the login. Sidecar mounts logs RO,
  has no network/socket/firewall capability, and runs the real fail2ban jail:
  five failures / 900 seconds, bantime 3600 seconds. Bans/DB survive restarts.
- `YACHT_HTTP_TRUSTED_PROXIES` is nginx's explicit IP/CIDR allowlist, generated
  by `backend/configure_nginx.py`; real-IP recursion skips trusted hops only.
  Backend `YACHT_TRUSTED_PROXIES` stays loopback. Never treat arbitrary private
  hops as trusted. nginx preserves forwarded HTTPS only from trusted peers.
- App image USER1000:1000; entrypoint never uses root, gosu or recursive chown.
  Both Compose files drop every app capability and use a read-only rootfs.
  Existing mounted data must already belong to 1000:1000; migration instructions
  are in `docs/SECURITY_DEPLOYMENT.md`. The daemon/socket proxy remain powerful
  infrastructure, and this setup does not automatically make Docker rootless.

### New workload and update contracts

- `utils/container_security.py` centralizes restricted defaults and allowed
  capabilities. DeployForm adds `security_profile`, `container_user`, and
  `confirm_image_default`. Restricted defaults 1000:1000, read-only rootfs,
  cap_drop ALL, no-new-privileges, pids 256, bounded/tmp+/run. Host networking and
  devices require explicitly confirmed `image-default`, active-superuser only.
  UI templates cannot select compatibility implicitly; legacy edits require
  a fresh acknowledgement. Edits require `perm_restart` in addition to create.
- Newly saved Compose files acquire explicit per-service restricted defaults.
  Literal `x-yachtplus-security: image-default` is the administrator escape.
  Includes must be inlined; restricted services reject namespace sharing,
  root users, dangerous caps, device exposure, traversing relative binds and
  custom volume drivers/options. Existing external YAML and running containers
  are not automatically rewritten; audit/migrate them before recreating.
- `utils/container_update.py` replaces the archived external Watchtower image.
  Disposable UID 1000 workers use the current Yacht image and only the configured
  TCP Docker proxy network (`YACHT_DOCKER_PROXY_NETWORK`); no host socket mount.
  Preserve volume identity, security options, aliases/static-IP settings and
  original image reference in `local.yachtplus.update.image` while pinning the
  pulled image ID. Drop generated old hostnames. Keep original until successful
  startup/health, restore it on error, attempt every rollback step despite
  secondary failures. Without an image healthcheck only startup is verified.
  A retained backup/finished worker is visible for operator inspection; completed
  workers can be cleaned before a later retry. Compose auto-update scheduler
  remains separate and still uses Docker Compose through the proxy.
- `utils/container_edit.py` retains the original during form edits, preserving
  anonymous volumes, static endpoints and health checks. An OS file lock
  serializes edits across API workers. Rollback attempts every recovery step.
  Labels `local.yachtplus.edit.transaction`, `local.yachtplus.deploy.transaction`
  and `local.yachtplus.update.transaction` prove ownership before uncertain
  creation cleanup; never delete an unproven container by name.
- Both Compose files label application/docker-proxy/fail2ban services with
  `local.yachtplus.infrastructure`. In-process form edits reject these roles
  and the actual application ID/configured proxy address. Update workers may
  replace YachtPlus itself, but reject the Docker proxy and protection service
  before spawning and again before any pull/stop. Change those with Compose.
- `/api/settings/deployment` recomputes diagnostics from the current persisted
  access policy; startup checks based on the historical login flag are not an
  access decision.
- `.gitattributes` forces LF for shell scripts even on Windows. A CRLF shebang
  prevents the Linux image entrypoint from executing; preserve LF when editing.
- The packaged image defaults `YACHT_FAIL2BAN_REQUIRED=true` too: a bare image
  cannot accidentally run without protection state. Direct source development
  defaults false. CI explicitly opts out only for isolated startup checks;
  publication additionally runs the protected stack against the exact candidate
  image ID before pushing it.
- `scripts/security-stack-smoke.py` must run on Linux with Docker/Compose; absent
  Docker is an error, never a skipped success. The required CI `security-stack`
  job validates actual bans/unbans, LAN/public/proxy/UI/API/WS, persisted bans,
  protection outage recovery, loopback backend and runtime permissions. GHCR
  publication requires its success in addition to backend/frontend/ruff jobs.


| Defense | Where | Notes |
|---|---|---|
| HttpOnly auth cookie | `api/auth/jwt.py: set_access_cookies` | JS cannot read the token. |
| Cookie CSRF / WS Origin | `api/utils/csrf.py` | Double-submit `csrf_access_token` / `X-CSRF-TOKEN` for mutations; exact scheme/host/port for browser Origin, including WS. |
| CSP | `api/main.py` `add_security_headers` | `script-src 'self' 'unsafe-inline'`. **No `unsafe-eval`** — keep it that way. |
| Trusted-host | `api/main.py` `_trusted_host_middleware` (custom, not Starlette's) | Reads `settings.ALLOWED_HOSTS`. Override with `YACHT_ALLOWED_HOSTS=…`. Rejects non-matching Host headers with 400. |
| CORS allowlist | `api/main.py` `CORSMiddleware` | Reads `settings.CORS_ORIGINS`. Override with `YACHT_CORS_ORIGINS=…`. Startup fails fast if list contains `*` (incompatible with `allow_credentials=True`) or an entry without a scheme. |
| HTML sanitisation | `frontend/src/main.js` `$sanitize` | DOMPurify with explicit allowlist; covers all `v-html` sites. |
| Per-IP login limit | `api/routers/users.py` `@limiter.limit("5/minute")` | slowapi on login + refresh + key-creation. |
| Per-IP fail2ban | `api/utils/security.py: check_ip_restriction` | 5 failed logins / 15 min from the same IP → 403. |
| Per-username lockout | same | 20 failed logins / 30 min for the same username (across IPs) → 403. Error wording is identical to the IP block so an attacker can't tell which guard fired. |
| Rate-limiting | `api/utils/security.py: limiter` | `_resolve_client_ip` key; `RATE_LIMIT_STORAGE_URI=memory://` and the image runs one gunicorn worker. Multiple workers require shared limiter storage and its client dependency; process-local memory cannot enforce a combined limit. Default 100/minute; mutation limits vary by endpoint. |
| Trusted-proxy allowlist | `api/utils/security.py: _is_trusted_proxy` | X-Real-IP / X-Forwarded-For are **only** honoured when the direct peer is in `settings.TRUSTED_PROXIES` (`YACHT_TRUSTED_PROXIES=ip[,cidr,...]`). Default loopback only → trusts the internal nginx. HTTP proxy trust is configured separately in nginx. Stops same-LAN attackers from spoofing client-IP attribution. |
| API-key delete | `api/routers/users.py: delete_api_key` | DELETE only. Ownership-or-superuser check in `crud.blacklist_api_key`; non-owner gets the same "not found" payload as a missing id (no IDOR leak). |
| API-key creation rate limit | `api/routers/users.py: create_api_key` | `@limiter.limit("5/minute")` — keys are long-lived (10y exp). |
| SECRET_KEY / salt | `api/settings.py`, `utils/secret_files.py` | Signing keys require at least 32 bytes. Fully written/fsynced mode-0600 temporary files are published atomically, so workers never read a partial key/salt. Existing invalid files fail rather than being replaced. Back up key, salt and DB together. |
| At-rest crypto | `api/utils/crypto.py` | PBKDF2-HMAC-SHA256 (600k iterations, persisted 16-byte salt at `FERNET_SALT_FILE`). New TOTP/SMTP writes use `v2:` Fernet ciphertext; legacy v1 remains readable. Alembic upgrades existing SMTP rows. Async crypto call sites run in threads. |
| 2FA enforcement | `api/routers/setup/setup.py: finalize_setup` | Setup cannot complete without 2FA enabled. |
| WS auth (exec) | `api/routers/containers.py` | Cookie-only handshake, never URL/query token. Shell-name whitelist → reject setup_pending → DB lookup → `perm_start` gate. See section 5 for the full chain. |
| Template SSRF mitigation | `api/db/crud/templates.py` | Validates each redirect and resolved IP, then connects to those exact addresses without a second DNS lookup. Proxy environment is ignored; non-global/special IP ranges are rejected. Fetch/body deadline 15 seconds and size limit 5 MiB. |
| Last-admin guard | `api/db/crud/users.py` | Database write lock serializes edits/deletes; at least one active superuser must remain. |
| SMTP | `api/routers/smtp.py`, `utils/smtp_delivery.py` | Admin-only, encrypted password, redacted response; TLS uses certificate validation, SMTPS on port 465 and bounded network timeout. |
| Activity retention | `utils/audit_middleware.py`, `services/watchtower.py` | Successful HTTP mutations and login outcomes are recorded without request bodies; hourly cleanup removes audit/login records after 90/30 days and expired blacklist entries. Ordinary audit storage failures are logged, not a durable/WORM guarantee. |

---

## 7. External integrations

| Integration | How | Env |
|---|---|---|
| Docker daemon (async) | `aiodocker.Docker(url=settings.DOCKER_HOST)` | `DOCKER_HOST` |
| Docker daemon (sync) | `api.utils.docker_client.get_sync_docker_client()` — wraps `docker.DockerClient(base_url=...)` when `settings.DOCKER_HOST` is set, else `docker.from_env()`. **Never call `docker.from_env()` directly** — it bypasses an operator-configured TCP proxy. | `DOCKER_HOST` |
| docker-compose CLI | `subprocess.run` inside `_run_compose_command` (array form, no `shell=True`), allowlisted environment and a dedicated two-thread executor. Whitelisted subcommands, 600-second timeout. | `COMPOSE_DIR`, `DOCKER_HOST` |
| Docker Hub / GHCR | HTTP for image metadata and image listing | — |
| Template registries | Bounded `urllib` fetch with DNS-pinned SSRF protection per redirect. Accepts Yacht and Portainer v2 wrapper formats. YAML aliases/deep documents are rejected by `utils/yaml_loader.py`. | `YACHT_DEFAULT_TEMPLATE_URLS`, `YACHT_BUILTIN_CATALOG_DIR` |
| Email (SMTP) | Encrypted DB credentials; `utils/smtp_delivery.py` centralizes verified TLS and timeout | — |

#### Least-privilege Docker socket proxy matrix (N-01/N-02)

When YachtPlus talks to Docker through `tecnativa/docker-socket-proxy`,
the proxy must allow the API sections the backend uses. This proxy grants
access by API section; flags such as `CONTAINERS_CREATE` and `DELETE` are not
supported by that image. Keep the matrix in sync with new Docker calls.

| Area | Proxy env flags needed | YachtPlus usage |
|---|---|---|
| Read resources | `CONTAINERS=1`, `IMAGES=1`, `NETWORKS=1`, `VOLUMES=1` | Dashboard stats, app list, resource lists, logs, inspect |
| Container lifecycle | `CONTAINERS=1`, `POST=1` | start / stop / restart / recreate / remove containers |
| Image management | `IMAGES=1`, `POST=1` | pull / prune / remove images |
| Network management | `NETWORKS=1`, `POST=1` | create / remove networks |
| Volume management | `VOLUMES=1`, `POST=1` | create / remove volumes |
| Exec (terminal) | `EXEC=1`, `POST=1` | `/api/containers/{id}/exec` WebSocket |
| Compose | `INFO=1`, `BUILD=1` plus the resource flags above | `docker compose` CLI runs inside YachtPlus and talks to the daemon through the proxy |

The `docker-compose.example.yml` ships with a read-only socket mount to the
proxy and an API-section allowlist. The mount's `:ro` flag does not make the
Docker API read-only: `POST=1` and container/build/exec routes grant extensive
control. Keep the proxy isolated on the Compose network.

**Pattern for sync I/O in async routes:** never call sync code from an `async
def` handler directly. Put the sync work in a `_xxx_sync` helper and call it
via `await run_in_thread(_xxx_sync, ...)` — see `actions/compose.py` for the
canonical example.

**Pattern for aiodocker:** one client per logical operation. When you need to
fan out across N containers (see `actions/apps.py: all_stat_generator`), open
one `async with aiodocker.Docker(...)` and pass it to per-container helpers.
Do not open one client per container in a loop.

### Async conventions (post-migration — follow these for new code)

The backend is fully async (SQLAlchemy `AsyncSession`, `async def` handlers).
Blocking / CPU-bound work must never run directly on the event loop:

- **DB:** always `await db.execute(select(...))`, `await db.commit()`,
  `await db.refresh(...)`, `await db.rollback()` on an `AsyncSession`. No
  `db.query(...)`, no sync `db.commit()`. Type-hint dependencies as
  `db: AsyncSession`.
- **bcrypt / hashing:** `get_password_hash` / `verify_password` in
  `db/crud/users.py` are async and internally run bcrypt via
  `asyncio.to_thread` — always `await` them.
- **SMTP:** `routers/smtp.py` `send_test_email` runs the blocking send in a
  sync helper via `asyncio.to_thread`; `security.py` `send_security_alert`
  does the same. Never `smtplib` directly in an `async def`.
- **psutil / system stats:** `actions/dashboard.py` runs `psutil.cpu_percent()`
  and `psutil.virtual_memory()` via `asyncio.to_thread`; the dashboard router
  wraps `shutil.disk_usage` via `asyncio.to_thread`.
- **subprocess / compose:** `actions/compose.py` keeps the sync
  `_compose_action_sync` / `_compose_app_action_sync` helpers and runs them via
  `await run_in_thread(...)` in its own bounded two-thread executor
  (array-form `subprocess.run`, no `shell=True`, no API secrets in child env).
- **Template fetches (SSRF):** `db/crud/templates.py` `_fetch_template_payload`
  is async and runs the urllib fetch in `_fetch_template_payload_sync` via
  `asyncio.to_thread`. The SSRF guards (`validate_url`, `SafeRedirectHandler`,
  `_SSRFGuardedHTTP*`) stay sync and run inside the thread — do not remove
  them.
- **QR code (2FA):** `routers/auth_2fa.py` runs qrcode generation in
  `_generate_qr_code_sync` via `asyncio.to_thread`.
- **Docker sync SDK:** wrap any `get_sync_docker_client()` calls in
  `asyncio.to_thread` / `run_in_thread`.
- **App start:** DDL happens in the `lifespan` hook
  (`await engine.run_sync(Base.metadata.create_all)`). Never call
  `Base.metadata.create_all(bind=engine)` on the async engine directly.

**Rule of thumb:** if a helper does blocking I/O or CPU-heavy crypto and is
called from an `async def`, it must be isolated (async library or
`asyncio.to_thread`). Pure formatting/validation helpers stay sync.

### Rules for new routes, services and DB access (post-migration)

1. **New routers / endpoints:** define `async def` handlers. Gate with
   `await auth_check(Authorize)` (data routes) or
   `await auth_check_setup_pending(Authorize, db)` (setup), and
   `await check_permission(...)` / `await require_superuser(...)` where needed.
2. **DB access:** use the async `get_db` dependency from `api.utils.auth`
   (yields `AsyncSession`). Write queries with `select(...)` +
   `await db.execute(...)` + `.scalars()/.first()/.all()`. Commit/refresh/
   rollback must be awaited. Never `db.query(...)`.
3. **New CRUD functions:** make them `async def` taking `db: AsyncSession`.
   Keep pure helpers (formatting, validation) sync.
4. **New external I/O** (SMTP, HTTP, subprocess, files, sync Docker SDK,
   psutil): never call blocking libs directly in an `async def`. Either use a
   native async library (aiodocker, httpx.AsyncClient, aiofiles, aiosqlite)
   or isolate via `asyncio.to_thread` / `run_in_thread`. Document the choice.
5. **CPU-heavy crypto** (bcrypt, PBKDF2) in request handlers: isolate via
   `asyncio.to_thread` — never hash/verify synchronously in the event loop.
6. **New services / background jobs:** APScheduler runs sync code in its own
   thread (see `services/watchtower.py`), so a sync function is fine there;
   it must not be called directly from an async handler.
7. **Audit:** `api/utils/audit.py` `log_activity` is async and must be awaited
   with an `AsyncSession`. The retention job uses a separate sync engine only
   inside APScheduler's thread and disposes it after each run.

### Known intentionally-sync exceptions (documented)

- `api/actions/compose.py` `_compose_*_sync` / `_get_compose_sync` are sync
  (subprocess + YAML) and are always invoked via `await run_in_thread(...)`.
- `api/db/crud/templates.py` `_fetch_template_payload_sync` /
  `_refresh_fetch_sync` are sync urllib fetches wrapped in
  `asyncio.to_thread` (keeps the connect-time SSRF re-validation intact).
- `services/watchtower.py` runs sync in the APScheduler thread by design.
- Template URL validation helpers (`validate_url`, `is_private_ip`,
  `_check_address_safe`) are sync CPU/DNS logic used inside the thread-bound
  fetch — do not convert them.

---

## 8. Conventions

| Artifact | Convention | Example |
|---|---|---|
| Backend module | snake_case | `auth_2fa.py` |
| Vue component | PascalCase | `ContainerTerminal.vue` |
| API route file | snake_case, mirrors feature name | `routers/apps.py` |
| Test file | `test_<module>.py` | `tests/test_auth_2fa.py` |
| DB table | snake_case singular | `user`, `template_item` |
| Env var | UPPER_SNAKE_CASE | `DATABASE_URL`, `YACHT_ALLOWED_HOSTS` |
| Frontend import alias | `@/...` → `frontend/src/...` | `import x from "@/utils/imageLogos"` |

### Frontend conventions (post-modernisation)

- **Lazy-loaded routes.** Every route component in `router/index.js` is
  `() => import(...)` so each page ships as its own chunk. When you add a
  route, keep it lazy — never add a static top-level import for a view.
- **Vendor code-splitting.** `vite.config.js` `build.rollupOptions.output.manualChunks`
  splits `vue-vendor`, `vuetify` and `axios` into cacheable chunks. Keep this
  list in sync if you add a heavy dependency.
- **Tree shaking and build gates.** Do not globally register `vuetify/components`
  or `vuetify/directives`; `vite-plugin-vuetify` auto-imports template usage.
  `npm run build` emits a manifest and runs `scripts/check-bundle.mjs` to check
  all assets and initial byte budgets (entry JS 300000, initial JS 550000,
  initial CSS 700000). Terminal, Compose editor and statistics stay lazy.
  Vite emits `dist/version.json` from the same resolved version as the UI;
  the build gate and candidate check compare it exactly, not by substring.
- **Lazy terminal and page failures.** ApplicationsList mounts `AsyncFeature`
  only when opening the terminal. It bounds loading to 15 seconds, provides
  retry/close, rejects malformed modules and invalidates late/unmounted work.
  `ChunkRecovery` uses `utils/chunkRecovery.js` to handle route import errors;
  keep the current page and inputs, offer retry and explicit reload. Never
  reload automatically or use this flow for authentication failures.
- **Shared search.** `GlobalSearch` and `UnifiedSearch` are wrappers around
  `SearchBox.vue`; shared result normalization lives in `utils/search.js`.
  Preserve local application filtering, full image namespaces, keyboard
  Up/Down/Enter/Escape and mobile access. Search failures are retryable;
  debounce, timeout/cancellation and generation guards prevent stale results.
- **Global snackbar.** `App.vue` mounts `components/notifications/snackbar.vue`
  once. Views push feedback via the `snackbar` Vuex module (`setErr`/`setSuccess`/
  `setMessage`) instead of `console.log`. The component uses Vuetify 3 `v-model`
  + `location` (not the Vuetify 2 `:value`/`:bottom`).
- **Theme.** `components/serverSettings/Theme.vue` uses Vuetify 3 theme state.
  Options API `$vuetify` access unwraps refs (`theme.global.name`,
  `theme.themes`); the direct instance in `plugins/vuetify.js` retains `.value`.
  Persists `dark_theme`,
  `theme_primary`, `theme_secondary` in `localStorage`. `App.vue` restores the
  theme on mount.
- **Terminal dependencies.** Use `@xterm/xterm` and `@xterm/addon-fit`;
  the retired `xterm` / `xterm-addon-fit` packages are removed. Terminal
  loading remains lazy. Fonts ship locally; no Google Fonts request is made.
- **Authentication state.** The auth store coalesces refresh requests. Logout
  clears account/setup secrets and user resource state; username/password
  changes require the existing password and return to login after revocation.
- **Logs and charts.** Log requests and in-browser history are bounded to
  10,000 lines; SSE `end`/`error` stops reconnect loops, and stopped containers
  can show historical logs. Docker memory charts subtract inactive cache.
- **Compose files.** Support `compose.yaml`, `compose.yml`, `docker-compose.yaml`
  and `docker-compose.yml`, with deterministic priority. Discover only direct
  project folders, skip symlinks, validate bounded mapping YAML before atomic
  save, and preserve the selected filename. Project deletion runs `down`
  before deleting files and preserves them on failure. Raw YAML is admin-only.
- **Templates.** Refresh is POST-only; eagerly load ORM items before async
  serialization. String commands are split into argument arrays; every port
  survives conversion and per-item refresh state must not leak to later rows.
- **Schedulers.** Hourly retention runs under one filesystem-elected leader.
  Daily Compose pulls/recreates require `COMPOSE_AUTO_UPDATE=true`; manual
  update endpoints await completion and propagate errors.
- **Dashboard polling.** `views/Home.vue` polls only while the tab is visible
  (`document.hidden` guard) and refreshes immediately on `visibilitychange`.
  Keep this pattern for any new auto-refresh view.
- **Vuetify 3 syntax.** Use `v-model`, `location`, `density`, `variant`,
  `v-icon start/end`, `v-tooltip location` — not the Vuetify 2 `:value`,
  `bottom`, `dense`, `outlined`, `dark`, `v-icon left/right`, `v-tooltip bottom`
  forms. `v-tabs-items`/`v-tab-item` are `v-window`/`v-window-item` in v3.
- **Form binding.** With vee-validate 4, bind each `Field` to its form value
  using `v-model` and pass its `componentField` slot props to Vuetify inputs.
  Native-input `field` props do not provide the component's `modelValue`
  contract. Repeated fields need unique names. Form validation uses the
  `meta` slot; never reference an unbound `meta` or nest HTML forms.
- **Deployment steps.** Use `v-stepper-item`, `v-stepper-window` and
  `v-stepper-window-item` with numeric values. The eagerly mounted step forms
  keep validation refs available; validate every step and Advanced before
  deploying. Advanced uses `v-expansion-panel-title`/`v-expansion-panel-text`.
- **Resource API lists.** GET lists return `{ items, total }`, not arrays.
  `utils/resourcePages.js` loads all pages before committing the table data.
  Resource actions return their promises; creation/deletion returns a boolean
  result so dialogs stay open on failure. Docker list timestamps for images
  are Unix seconds; image inspect timestamps are ISO strings.
- **Docker resource usage and prune.** Container inventory from aiodocker
  contains `DockerContainer` objects; `actions/resources.py` reads their
  attached `_container` metadata. Inventory errors are errors, never empty
  successful lists or an "unused" signal. The installed aiodocker has no
  collection `prune()` methods; use its `_query_json` with the allowlisted
  Engine prune endpoint. Preserve Docker's `*Deleted`/`SpaceReclaimed` result
  keys and do not report failed pruning as success.
- **Displayed version.** Vite defaults `VITE_VERSION` to the canonical
  `frontend/package.json` version, while honoring an explicit build value.
  Sidebar and settings use the same value; do not hardcode a UI version or
  a Docker connection status.
- **Activity tracking.** `App.vue` `startActivityTracking()` is idempotent
  (guarded by `_activityTrackingStarted`) so listeners are never double-
  registered.

**Comments:** the codebase has a lot of historical inline commentary (decisions,
abandoned approaches, ASCII trace logs). When you touch a function, prune the
stale comments along the way — don't add to the pile.

**Error envelope:** all API errors return `{"detail": "..."}` (FastAPI default).
Frontend reads `err.response?.data?.detail` and surfaces it via `snackbar/setErr`.

**Global error handling:** `api/main.py` registers `unhandled_exception_handler`
(500 → generic `{"detail": ..., "trace_id": ...}`, full traceback logged
server-side) and `validation_exception_handler` (422 → sensitive fields masked,
never echoed back). Both live in `api/utils/error_handler.py`.

---

## 9. Local development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\Activate.ps1 on Windows
pip install --require-hashes -r requirements-dev.lock
# uvloop is skipped automatically on Windows by its dependency marker.

export DATABASE_URL="sqlite:///./local.db"   # avoid /config/yacht.db
uvicorn api.main:app --reload --port 8000
```

### Frontend

Use Node.js `^20.19.0 || >=22.12.0`, matching Vite's supported engines.

```bash
cd frontend
npm ci
npm run dev      # Vite on :8080, proxies /api → :8000
# or
npm run build    # writes to frontend/dist
```

### Tests

The test suites live in `backend/tests/` and `frontend/**/*.test.js` and are
**tracked**; CI runs them on every push/PR. To run them locally:

```bash
# Backend
cd backend
DATABASE_URL="sqlite:///./test.db" python -m pytest tests/

# Frontend
cd frontend
npm run test
```

Useful subsets:
- `python -m pytest tests/test_smtp.py` — SMTP fixes and debounce.
- `python -m pytest tests/test_compose_perms.py tests/test_compose_delete_path.py` — compose permission and path-safety gates.
- `python -m pytest tests/test_image_inspect.py` — Docker Hub manifest/tag handling.

Local verification before remote integration on 2026-10-02 passed **852 backend, 197 frontend and 42
publication-policy tests**. The latest [changelog](CHANGELOG.md) entry and
[remediation report](docs/AUDIT_REMEDIATION_2026-10-02.md) record build/migration
evidence and remaining Docker/runtime checks. Historical audit test counts
are not the current baseline.
Run the independent publication policy suite from the repository root with
`python -m unittest discover -s scripts -p 'test_*.py' -v` (using the
backend environment, which includes PyYAML). It exercises policy failures,
real Git ref/checkout changes, workflow dependencies and the image secret-file
guard (including a failed filesystem scan with empty output). CI runs it before
the Docker smoke build.

`backend/tests/conftest.py` also provides shared async `db` / `db_session`
fixtures (in-memory `sqlite+aiosqlite`, `StaticPool`). After the async
migration, every test that touches the DB uses an `AsyncSession`;
`MockAuth`-style classes in tests have `async def jwt_required()` /
`async def get_jwt_subject()`.

---

## 10. Database / migrations

- Models in `backend/api/db/models/`. Adding a column? Add it to the model
  and create an Alembic revision in `backend/alembic/versions/`.
- `start.sh` runs `alembic upgrade head` before nginx and gunicorn. Alembic
  creates the initial schema on fresh installs and applies versioned changes.
  The FastAPI lifespan also calls `Base.metadata.create_all` via
  `engine.run_sync` as an idempotent safeguard.
- The `User` model encrypts `otp_secret` at rest via `api.utils.crypto`.
  Don't write plain TOTP/SMTP secrets to the DB. Revision `20261001_0001`
  adds `auth_version` and `otp_last_step`, encrypts older SMTP passwords, and
  converts affected PostgreSQL timestamps to UTC-aware columns. Existing
  sessions/API keys without the account version require login/recreation.
  Back up the database, signing key and Fernet salt together before upgrading.

---

## 11. Configuration (env vars)

| Var | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | — | JWT signing key, at least 32 bytes. If unset, read/create `SECRET_KEY_FILE`; never use an ephemeral fallback. |
| `SECRET_KEY_FILE` | `/config/.secret_key` | Atomic persisted signing key; default falls back to `.secret_key` in cwd when `/config` does not exist. Existing invalid files fail startup. |
| `FERNET_SALT_FILE` | `/config/.fernet_salt` | Atomic persisted 16-byte crypto salt; falls back to `.fernet_salt` in cwd if the parent directory is absent. Preserve alongside key and database. |
| `ENVIRONMENT` | `development` | Deployment-mode diagnostics; does not alone enable the cookie `Secure` flag. |
| `SECURE_COOKIES` | auto per request | Explicit true/false override; otherwise HTTPS/trusted proxy scheme controls `Secure`. |
| `SAME_SITE_COOKIES` | `lax` | Cookie SameSite attribute; separate CSRF proof is still required for cookie mutations. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Normal session-token and matching cookie lifetime; setup tokens use 15 minutes. |
| `DATABASE_URL` | `sqlite:////config/yacht.db` | SQLAlchemy URL. |
| `YACHT_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | TrustedHostMiddleware list. |
| `YACHT_ALLOW_PRIVATE_NETWORK_HOSTS` | `false` in source | Permit private/link-local IP literal Host headers as a convenience; Compose explicitly enables LAN literal hosts. Prefer explicit names where possible. |
| `YACHT_CORS_ORIGINS` | localhost variants | CORS origin list. Startup fails fast if it contains `*` or an entry without scheme. |
| `YACHT_TRUSTED_PROXIES` | `127.0.0.1,::1` | Backend peers allowed to supply client headers. Keep loopback in the nginx image; configure external proxy trust separately below. |
| `YACHT_HTTP_TRUSTED_PROXIES` | empty | External IP/CIDR allowlist validated by `configure_nginx.py` for nginx real-IP and HTTPS attribution. |
| `YACHT_BLOCK_PUBLIC_IP_LOGIN` | `true` | Legacy compatibility setting; cannot enable public access or bypass the global persisted access policy. |
| `YACHT_ACCESS_POLICY_FILE` | `/config/access-policy.json` | Persisted explicit public-access opt-in; absent means LAN-only. |
| `YACHT_FAIL2BAN_REQUIRED` | `false` in source; `true` in image/Compose | Required fail2ban readiness; public access always requires mandatory healthy protection. |
| `YACHT_FAIL2BAN_STATE_DIR` | `/run/yachtplus-security` | Read-only app mount for sidecar readiness and bans. |
| `YACHT_SECURITY_LOG` | `/config/security/auth.log` | Persistent deterministic login-failure log consumed by fail2ban. |
| `COMPOSE_DIR` | `/compose/` | Canonically joined project paths; trailing slash optional. |
| `COMPOSE_AUTO_UPDATE` | `false` | Opt in to the leader's daily Compose pull/recreate job; manual updates remain available. |
| `AUDIT_RETENTION_DAYS` | `90` | Hourly cleanup retention for activity records; minimum 1. |
| `LOGIN_RETENTION_DAYS` | `30` | Hourly cleanup retention for login-attempt records; minimum 1. |
| `RATE_LIMIT_STORAGE_URI` | `memory://` | slowapi storage backend. Image uses one worker; custom multiworker deployments require shared storage and its client dependency. |
| `YACHT_DEFAULT_TEMPLATE_URLS` | SelfhostedPro and Portainer Community URLs in `settings.py` | Comma-separated `Title\|URL` registry seeds during first finalize; an empty value disables remote seeding. Fetch failures do not block setup. |
| `YACHT_BUILTIN_CATALOG_DIR` | `/api/configs` | Bundled `*.json` catalogs available during setup without a remote download. |
| `SETUP_FLAG_FILE` | `/config/.setup_completed` | Legacy setup marker, restricted to `/config` or cwd; setup-complete checks consult DB status and this fallback marker. |
| `ENV_FILE` | unsupported | Historical runtime environment-file override; current settings read `.env` via Pydantic and this variable has no effect. |
| `DOCKER_HOST` | (unset → SDK default = `/var/run/docker.sock`) | Docker connection. Declared as `Optional[str]` on Settings; when set, **both** the async (`aiodocker`) and sync (`utils/docker_client`) paths honour it. |
| `YACHT_DOCKER_PROXY_NETWORK` | `${COMPOSE_PROJECT_NAME:-yachtplus}_docker_api` in Compose | Network for isolated update workers; no host socket mount. |
| `DISABLE_AUTH` | `False` | **Dev only.** Bypasses every auth check. Never set in prod. |

---

## 12. High-risk areas — extra caution required

| Area | Why | Required action before merging |
|---|---|---|
| Anything in `api/auth/` or `api/routers/setup/` | One broken assertion = auth bypass | Add or extend a pytest case in `tests/test_auth*.py` or `test_setup.py`. Run the full setup flow manually if behaviour changes. |
| Adding a new `/api/*` route | Default is "blocked by middleware" | Decide consciously: data route (`auth_check`) vs setup route (`auth_check_setup_pending`) vs public (whitelist in middleware). |
| Container logs | Logs often contain secrets / tokens | `get_container_logs` requires `auth_check` **and** `check_permission("perm_start", Authorize, db)`. |
| Returning docker/subprocess errors to the client | Information disclosure: daemon paths, hostnames, env values, possibly secrets | Use `api.utils.error_handler.docker_error_detail()` for aiodocker exceptions and generic messages for compose/subprocess failures. Log full details server-side. |
| User-supplied URL fetched server-side | SSRF risk | Reuse `api/db/crud/templates.py` guarded handlers: validate each resolved address and redirect, connect to those exact addresses, disable environment proxies, bound both bytes and the total body deadline. Validation followed by ordinary DNS reconnect reintroduces rebinding. |
| User-supplied YAML | Alias amplification, deep nesting and unsafe Compose files | Reuse `utils/yaml_loader.py`, bound input bytes and require a mapping. Validate workload profiles before atomic write; never delete a stack's files before successful `down`. |
| Subprocess / shell invocation | Command injection | No `shell=True`. Pass args as a list. Validate every component if it came from request data. Subcommand whitelist at the action layer too, not just the router (see `_ALLOWED_PROJECT_ACTIONS`). |
| Adding a query/path arg that becomes a subprocess token, exec command, or shell binary | Same | Whitelist at both router and action layer. Reject before any auth check if the value is suspicious — keeps token-probing attempts from getting any signal. The container-exec WS `shell` param is the canonical example. |
| Touching the cookie name, `setup_pending`, or `is_active` semantics | Frontend depends on the exact strings/shape | grep both backend and frontend for the symbol before changing. |
| Removing `unsafe-eval` from CSP is a non-goal — it's already removed. Adding it back is a no. | XSS surface | If a dep needs `unsafe-eval`, the dep is the problem. |
| Adding `settings.X` reference for a new env var | Pydantic `Settings` uses `class Config: env_file=".env"` (no `extra` set) | Declare `X` as a field on the `Settings` class in `api/settings.py`. Otherwise the read crashes with `AttributeError` at request time. `tests/test_settings_fields.py` pins the must-exist contract for the currently-declared fields. |
| Calling `docker.from_env()` | Bypasses `settings.DOCKER_HOST` | Always go through `api.utils.docker_client.get_sync_docker_client()` for the sync SDK. |
| Generating a JWT signing key | `HS256` needs >= 32 bytes of raw entropy | `secrets.token_urlsafe(48)` in `api/settings.py`; never use `token_urlsafe(32)` or shorter. |
| Hashing a user password | bcrypt cost factor | Use `bcrypt.gensalt(rounds=13)` via `api.db.crud.users.get_password_hash()`. Verify via `asyncio.to_thread(bcrypt.checkpw, ...)`. |
| Trusting `X-Real-IP` / `X-Forwarded-For` outside `_resolve_client_ip` | IP-spoofing for rate-limit evasion | Don't. There's one entry point and it requires the peer to be in `settings.TRUSTED_PROXIES`. |
| Logging shell input/output, terminal frames, JWTs, or DB rows containing secrets | Sensitive data in logs | Log lengths, ids, or sanitised summaries — never the raw bytes. Semgrep's log-leak rule is configured to flag this. |

---

## 13. Common gotchas

- **`/config` doesn't exist outside Docker.** Override `DATABASE_URL` for
  local dev. Default signing-key/salt paths fall back to cwd; use explicit
  persistent local paths when managing multiple checkouts. Keep these files
  out of source control and image build contexts.
- **`uvloop` doesn't build on Windows.** Its dependency marker in
  `requirements.txt` skips it automatically on Windows. The release image
  uses Linux and includes it.
- **Two setup flag sources:** `is_setup_completed_async(db)` (async) checks
  both the `SetupStatus` table *and* the legacy `/config/.setup_completed`
  file. The sync `is_setup_completed(db)` wrapper still exists for pure-sync
  callers. If you reset state, kill both.
- **The `User.is_active` flag** is the "setup finalized" gate. New admins
  are created with `is_active=False`; `finalize_setup` flips it. Don't
  short-circuit this in tests by directly creating active users for the
  registration path.
- **JWT max_age must match `expires_delta`.** When you mint a token with a
  custom lifetime (e.g. setup-pending), pass the same value to
  `set_access_cookies(..., max_age=...)`. Otherwise the cookie outlives
  the JWT and vice versa.
- **Credential migration requires login.** JWTs lacking a matching `av` are
  rejected. Do not weaken version checks to keep old cookies/API keys alive;
  clear the browser session and create replacement API keys after upgrade.
- **TOTP codes are single use per step.** A code consumed by setup/enable,
  login or disable cannot be reused immediately. Wait for the next code when
  a subsequent operation needs confirmation.
- **Memory rate limits require one worker.** The image starts one gunicorn
  worker; changing the process count without shared storage multiplies limits.
- **Runtime dependencies are locked.** `requirements.txt` is the input,
  `requirements.lock` is the hashed runtime resolution; regenerate the lock
  when dependencies change. `requirements-dev.lock` is a separate hashed
  development resolution constrained by the runtime lock; pytest tooling
  and test sources are excluded from the image. CI uses the development lock,
  Docker uses the runtime lock and installs its exact built wheels offline.
- **TestClient sends `Host: testserver`.** Already handled by
  `tests/conftest.py`, but if you spin up a separate test harness, add
  `testserver` to allowed hosts.
- **`settings.X` for an unknown field crashes.** Pydantic v2 `Settings` uses
  `class Config: env_file=".env"` (no `extra` guard). A code reference to an
  undeclared field still bombs at runtime with `AttributeError`. Add the
  field to `api/settings.py`.
- **Async tests use `AsyncSession`.** After the async migration, every DB
  test uses an async in-memory engine; `MockAuth`-style test classes have
  `async def jwt_required()` / `async def get_jwt_subject()`. Never call an
  async router/CRUD/`auth_check` without `await` in tests.
- **Push policy.** This repo pushes directly to `master`; PRs are only used
  when the harness blocks the direct push (typically: destructive ops,
  unfamiliar branches). Don't open PRs by default — see the memory file
  `feedback_push_direct_to_master.md`.

---

## 14. Where to look first when something breaks

| Symptom | First place to look |
|---|---|
| 428 on every API call | Setup not finalized. Open `/setup` in browser. |
| 403 "Setup is pending, restricted access" | Stale `setup_pending=True` cookie. Logout, login again. |
| 401 immediately after login | Cookie domain / CORS mismatch. Check `YACHT_CORS_ORIGINS` and `Secure` flag vs HTTP/HTTPS. |
| 400 on every request from a specific host | Add the host to `YACHT_ALLOWED_HOSTS`. |
| `RuntimeError: SECRET_KEY could not be loaded` | `SECRET_KEY_FILE` path not writable. Set `SECRET_KEY` env or mount a writable `/config`. |
| `ModuleNotFoundError: uvloop` on Windows | See "common gotchas". |
| Pytest fails with `unable to open database file` | `DATABASE_URL` not set; defaults to `/config/yacht.db`. Set `DATABASE_URL="sqlite:///./test.db"`. |
| Frontend build red on `vee-validate`/`vue-chartjs` | These are real packages (`package.json`), not shims. If they don't resolve, run `npm install`. |

The longer triage checklist lives in [DEBUGGING_CHEATSHEET.md](DEBUGGING_CHEATSHEET.md).

---

## 15. When you finish a change

1. Run both test suites — they must stay green.
2. **Update AGENTS.md in the same commit if any of the following changed:**
   - directory layout, new/renamed module, new router or middleware
   - auth flow, cookie shape, token claims, middleware order
   - env var added / renamed / default changed (section 11)
   - external integration added or swapped (section 7)
   - dependency added/removed/upgraded that affects how to run things
   - new high-risk surface → add a row to section 12
   - new common gotcha discovered → add to section 13
   - test baseline numbers (sections 2, 9) changed
3. If you changed user-facing behaviour, also update [README.md](README.md).
4. If you removed a feature, search globally and delete every reference
   (code, tests, docs, settings) — don't leave dangling mentions in this
   file either.

---

## 16. Versioning

### Publication path

`ci.yml` is the only GHCR publisher. Its final `publish` job depends on the
same run's backend, frontend and informational Ruff jobs; do not restore
independent publishers or use privileged `workflow_run`/cross-run artifacts.
`scripts/release_gate.py` rejects PR/manual/fork/cancelled/failed/skipped runs,
modified checkouts, mismatched commit/ref or package/lock versions, noncanonical
tags and commits outside `master`. Only trusted `master` pushes or matching
`vMAJOR.MINOR.PATCH` tag pushes qualify. Candidate contents, exact version
metadata/OCI labels, startup and Docker health must pass before GHCR login.
`.dockerignore` excludes local credentials and SQLite files; the smoke test
rejects packaged signing keys, salts, `.env` files and runtime databases in
`/api` and `/config` before importing the backend (which initializes secrets).
The remote ref is checked again before login; the tested image ID is pushed
without rebuilding. Version tags do not move `latest`; master publication does.
Tag pushes are sequential, so an interruption can leave some tags published.

### Version rules

Use `MAJOR.MINOR.PATCH`. A change that receives its own dated entry in
`CHANGELOG.md` must bump the YachtPlus version in the same change. If the
classification is unclear, use PATCH. Passing tests without the required
version bump does not complete the change.

The sole exception is a documentation correction that extends an existing
entry for the **same** delivery. It stays in that entry and does not create a
new version. A separate dated documentation entry follows the normal PATCH
rule.

| Level | Use for | Evidence required before the bump |
|---|---|---|
| PATCH (`x.y.Z`) | Bug fixes, maintenance and standalone documentation changes without a compatibility break. | Backend pytest suite, frontend Vitest suite, production frontend build and a fresh-database Alembic upgrade pass. |
| MINOR (`x.Y.z`) | New, backward-compatible functionality or a newly declared stable release. | PATCH checks **plus** a successful Docker release-image build, image smoke test, start and health check, and a visual check of every changed UI flow in the running application. A bundle that merely builds is insufficient. |
| MAJOR (`X.y.z`) | Breaking behavior, API, configuration or persistent-data changes. | MINOR checks **plus** a documented manual run of the affected setup, upgrade and migration paths, including the compatibility decision for existing deployments. |

The gate is the important part of the level. Do not label an unstarted or
uninspected image as a verified MINOR or MAJOR release. If a required check
cannot run, record that limitation and leave the release claim open.

When increasing a component, reset every component to its right to zero;
for example `2.3.4` becomes `2.4.0` for MINOR or `3.0.0` for MAJOR. Increase
only one component per change: a MINOR bump already includes its PATCH fixes.

`frontend/package.json` is the canonical project version. Update
`frontend/package-lock.json` in the same change and verify both versions
match. Do not independently edit a second version constant. For a release
image, pass the canonical version as `VITE_VERSION` and verify the version
shown in the UI and any versioned image tag match it. `latest` and SHA tags
alone do not establish a SemVer release version.

Each version bump needs its own dated `CHANGELOG.md` entry stating the
change, completed checks and known limits. If an image was built, include
its image reference, size and SHA-256 digest when available. A GitHub Actions
build log is evidence for the checks it actually ran; it does not replace
the visual or manual checks required above.

---

## 17. Backwards-compatibility carve-outs

These names still contain the historical `yacht` token. **Don't rename them**
without a coordinated migration — they're persisted on user systems.

- `/config/yacht.db` — default SQLite path. Renaming would orphan every
  existing deployment's database.
- Docker container labels `local.yacht.port.<port>` — written into managed
  containers' label set so the UI can surface port descriptions. Renaming
  loses labels on all already-deployed apps.
- Env-var namespace `YACHT_ALLOWED_HOSTS`, `YACHT_CORS_ORIGINS` — public
  settings users put in their `docker-compose.yml`. Treat as stable API.

If you ever need to migrate any of these, do it gracefully: read both the
old and new name, log a deprecation warning, document the change in README.

## 18. Notes & journals

`.Jules/` holds free-form journal files from past agent runs
(`palette.md`, `sentinel.md`, `mechanic.md`, `bolt.md`). They are reference
notes, not policy. Read them if you want historical context; don't treat
them as ground truth — verify against current code.

`SECURITY-AUDIT.md`, `PROGRESS.md` and `CODEQL-TRIAGE.md` preserve historical
findings/decisions and explicitly identify outdated claims. Their old test
counts and open/closed labels do not establish current verification or live
GitHub alert state. The README, this file, latest changelog and current
[remediation report](docs/AUDIT_REMEDIATION_2026-10-02.md) describe the current
implementation and remaining checks.
## Speicherplatz — Pflicht bei JEDEM Durchlauf

- Nach jedem Lauf nicht mehr benötigte eigene Build-/Test-Artefakte und
  Caches entfernen; die frühere Container-Umgebung hatte knappen Speicherplatz.
- Benötigte Prüfnachweise erhalten und wiederverwendbare `.venv`/`node_modules`
  nicht pauschal löschen. Nur eigene, eindeutig identifizierte temporäre
  Ausgaben bereinigen; keine fremden Änderungen oder globalen Werkzeug-Caches.
- Dateien/Downloads innerhalb des Projektordners oder eines ausdrücklich
  freigegebenen temporären Arbeitsverzeichnisses halten. Auf Windows absolute
  Zielpfade prüfen und native PowerShell-Dateioperationen verwenden.


---

## 19. Historische Audit-Befunde (2026-09-10)

> Archiv des damaligen Befund- und Run-Standes. Zeilennummern, Paket-APIs,
> offene Restpunkte und grüne CI-Angaben unten beschreiben frühere Commits.
> Sie sind keine aktuelle Aufgabenliste oder Freigabe. Für den aktuellen
> Stand gilt der [Behebungsbericht](docs/AUDIT_REMEDIATION_2026-10-02.md);
> Angaben stets am aktuellen Code verifizieren. Die Remote-Integration
> erfordert erneute Tests des zusammengeführten Standes.

> **Damals dokumentierter Status:** Stand Run R-020, Commit `aed5e1f`; alle 28 Befunde der Tabellen 19.1 bis 19.3 seien umgesetzt und verifiziert (Backend 543 Tests, Frontend 21 Tests, Vite-Build grün, beide GitHub-Workflows grün); offen blieben M13 (Vuetify-3-Migration der `v-list-item`-Elemente) und L3 (`plugins/notifications.js` als toter Code); weitere damalige Restpunkte in Abschnitt 19.6. Das ist ein historischer Bericht, kein erneut erhobener Nachweis.

Ergebnis einer Code-Analyse (zwei Subagenten, Modell DeepSeek 4.1 Flash). **Jeder**
Eintrag unten wurde vom Hauptagenten anschließend gegen den echten Code verifiziert
(Zeilennummer, Bibliotheks-API, Laufzeitverhalten). Falschmeldungen der Subagenten
sind in Abschnitt 19.4 separat aufgelistet; die damalige Einstufung vor einer
aktuellen Änderung am Code erneut prüfen.

Legende: Sev = Severity (critical / high / medium / low). "ungeprüft" heißt: am Code
belegt, aber nicht zur Laufzeit bestätigt (venv/node_modules wurden aus
Speicherplatzgründen entfernt, daher war kein Build/Test möglich).

### 19.1 High — historischer Befundstand

| # | Stelle | Sev | Befund | Fix |
|---|--------|-----|--------|-----|
| H1 | `frontend/src/views/Home.vue:285` | high | `axios.get("/containers/stats")` — diese Route existiert NICHT (der Router bietet nur `/`, `/{id}/stats`, `/{id}/logs`). Jeder Poll in `pollAll()` läuft auf 404, die Dashboard-Kacheln bleiben dauerhaft leer. | Aggregat-Route `GET /containers/stats` im Backend ergänzen ODER auf `GET /dashboard/stats` umstellen. |
| H2 | `frontend/src/views/Home.vue:349` | high | Container-Aktionen gehen als `axios.get(\`/containers/${appName}/${action}\`)` raus. Das Backend verlangt `POST /containers/{id}/start|stop|restart`; `remove` ist `DELETE`. Ergebnis: 405, keine Aktion wirkt. | `axios.post` für start/stop/restart, `axios.delete` für remove. |
| H3 | `frontend/src/components/serverSettings/ServerUpdate.vue:61` | high | `checkUpdate()` sendet `POST /settings/check/update`; im Backend (`app_settings.py:152`) ist die Route `@router.get`. → 405, `updatable` bleibt `false`, der Update-Button ist dauerhaft gesperrt. | `method: "GET"` setzen. |
| H4 | 7 Listen-Komponenten (siehe Fix) | high | Vuetify 3 ruft den `@click:row`-Handler mit `(event, { item, index })` auf. Alle Handler lesen Argument 1 als Item → `item.Id` ist `undefined` → Navigation nach `/…/undefined`. Betroffen: `ImageList.vue:242`, `VolumeList.vue:278`, `NetworkList.vue:221`, `NetworkDetails.vue:334`, `TemplatesList.vue:352`, `ProjectList.vue:304`, `ApplicationsList.vue:426`. | Signatur auf `handleRowClick(event, { item })` umstellen (7 Stellen). |
| H5 | `frontend/src/components/resources/networks/NetworkForm.vue:187` | high | `:disabled="!meta.valid"` steht im Scope von `<Form v-slot="{ invalid }">` (Zeile 4) — `meta` ist dort nicht destrukturiert → `undefined` beim Rendern, Formular „Create Network" bricht ab. | `v-slot="{ invalid, meta }"` oder `:disabled="invalid"`. |
| H6 | `frontend/src/components/serverSettings/ServerVariables.vue:71` | high | `:disabled="!fieldMeta.valid"` steht AUSSERHALB des `<Field>`-Slots (der Save-Button liegt auf Form-Ebene). `fieldMeta` ist dort nicht definiert → Render-Fehler. Der frühere „F17"-Fix hat nur `meta` in `fieldMeta` umbenannt und damit nichts behoben. | `:disabled="invalid"` (Form-Scope) verwenden. |
| H7 | `frontend/src/components/resources/networks/NetworkDetails.vue:27` | high | Template ruft `router.push({ name: 'Networks' })`; es gibt weder eine `data`-Property `router` noch ist der globale Bezeichner in Vue-3-Templates auflösbar → TypeError. | `this.$router.push(...)` über eine Methode (wie `goBackToNetworks` in derselben Datei). |
| H8 | `frontend/src/components/serverSettings/ServerInfo.vue:33` | high | Der Import-Button ruft `import_settings(importFile)`, wobei `importFile` die `data()`-Property ist (nie gesetzt, bleibt `null`). Der File-Input ist inzwischen an `field.value` gebunden, der Klick-Handler aber nicht → `formData.append("upload", null)` sendet den String „null". | Feldwert an den Handler geben (`field.value`) oder die Property mitpflegen. |
| H9 | `backend/api/db/database.py:9-13` | high | `db_url.startswith("sqlite")` + `replace("sqlite:///", "sqlite+aiosqlite:///")` verdoppelt bereits async-fähige URLs: `sqlite+aiosqlite:///x` → `sqlite+aiosqlite+aiosqlite:///x` (der Teilstring `sqlite:///` steckt in `aiosqlite:///`) → `NoSuchModuleError` beim Start. Verifiziert per Python-Ausdruck. Greift, sobald jemand die in AGENTS.md §11 dokumentierte async-Form setzt. | Prefix exakt prüfen (`startswith("sqlite:///")`) und nur dann ersetzen; für `postgresql`/`mysql` analog. |
| H10 | `backend/api/routers/smtp.py:76` | high | `GET /api/settings/email` ist nur mit `auth_check` geschützt, liefert aber `SMTPSettingsSchema` inklusive `password` im Klartext an JEDEN authentifizierten Nutzer (POST/`/test` nutzen dagegen `require_superuser`). | `require_superuser` ergänzen und `password` aus dem Response-Modell nehmen. |

### 19.2 Medium — historischer Befundstand

| # | Stelle | Sev | Befund | Fix |
|---|--------|-----|--------|-----|
| M1 | `backend/api/routers/containers.py:477` | medium | `docker.executes.object(exec_id)` — das Attribut `executes` existiert in aiodocker nicht (Sub-APIs sind u.a. `containers`, `images`, `volumes`, `networks`, `system`). Der `AttributeError` wird vom umgebenden `except Exception: pass` geschluckt, der Resize Aufruf ist toter Code (kein Crash, `docker.close()` läuft). | `exec_obj = docker.containers.exec(exec_id)` (laut aiodocker-API: „Return Exec instance for already created exec object"). |
| M2 | `backend/api/auth/auth.py:44-92` | medium | Weder `check_permission` noch `require_superuser` prüfen `User.is_active`. Ein deaktivierter Nicht-Admin behält seine Rechte bis zum Token-Ablauf. Nur `/auth/refresh` und der WS-Exec-Pfad prüfen das Flag. | `is_active` in beiden Gates erzwingen (403/401). |
| M3 | `backend/api/utils/security.py:147` | medium | `X-Real-IP` wird bei vertrauenswürdigem Proxy ungeprüft als Client-IP übernommen (kein `ip_address()`-Parsing), anders als die XFF-Auswertung daneben. Ein frei wählbarer String landet im Rate-Limit-Schlüssel und in den Fail2Ban-Zählern. | Headerwert parsen; bei ungültigem Wert auf Direkt-Peer/XFF zurückfallen. |
| M4 | `backend/api/utils/security.py:221` | medium | `await send_security_alert(...)` läuft inline in `check_ip_restriction`, also im Login-Pfad. DNS + SMTP blockieren damit den Request (daher der 10-s-Timeout), und jeder Login von öffentlicher IP erzeugt eine Mail. | Alert per `asyncio.create_task`/BackgroundTask absetzen und pro IP/Zeitfenster throtteln. |
| M5 | `backend/api/main.py:192` | medium | `hostname = host_header.split(":")[0]` zerstört IPv6-Hosts: `::1` → `""`, `[::1]:8080` → `"["`. Der dokumentierte Default-Eintrag `[::1]` in `YACHT_ALLOWED_HOSTS` kann dadurch niemals matchen → 400 für IPv6-Clients. | `urllib.parse` verwenden bzw. bei nicht geklammerter IPv6 korrekt trennen. |
| M6 | `backend/api/db/crud/settings.py:45` | medium | `generate_secret_key` schreibt `get_settings().SECRET_KEY` (den JWT-Signing-Key) im Klartext in die DB-Tabelle `secret_key`. | Persistierung entfernen oder nur nach `SECRET_KEY_FILE` schreiben. |
| M7 | `backend/api/utils/registries.py:351` | medium | `…get('tags', [])` liefert `None`, wenn eine GHCR-Version den Key `tags` mit Wert `None` hat; anschließend `flat_tags.extend(None)` → `TypeError`, vom `except` verschluckt → `/api/registries/tags` antwortet still mit `[]`. | `…get('tags') or []`. |
| M8 | `backend/api/actions/apps.py:211` | medium | `raise HTTPException(status_code=503, detail=f"Docker Connection Error: {str(e)}")` gibt rohe Exception-Texte (inkl. Daemon-URL/Pfade) an den Client, obwohl alle anderen Docker-Pfade bewusst gesäubert sind. | Generische Meldung, Details nur serverseitig loggen. |
| M9 | `frontend/src/store/modules/volumes.js:100` | medium | `router.push({ name: "Volumes" })` steht im `finally` → Navigation auch bei Fehlschlag. Inkonsistent zum bereits behobenen Muster in `projects.js`/`images.js`/`networks.js` (dort via `then`). | `router.push` in den `then`-Zweig verschieben. |
| M10 | `frontend/src/store/modules/templates.js:139` | medium | Analog zu M9: `router.push({ name: "View Templates" })` im `finally`. | Wie M9. |
| M11 | `frontend/src/main.js:52` | medium | Es wird nur `$notify` (console.log-Stub) registriert, aber KEIN `$toast`. Damit sind alle `if (this.$toast) …`-Fehlermeldungen in `ContainerLogs.vue`, `RegistryBrowser.vue`, `DockerHubTemplates.vue` faktisch still — Fehler erreichen den Nutzer nie. | `$toast` als globalProperty registrieren, an den `snackbar`-Store gebunden. |
| M12 | 34 Fundstellen in `frontend/src/**/*.vue` | medium | `v-simple-table` wurde in Vuetify 3 zu `v-table` umbenannt; das alte Element ist kein gültiger Baustein mehr → Tabellen in Detailseiten rendern nicht (u.a. `ImageDetails.vue:157`, `VolumeDetails.vue:96`, `NetworkDetails.vue:127/200`). | `v-simple-table` → `v-table`. |
| M13 | 363 Fundstellen in `frontend/src/**/*.vue` | medium | `v-list-item-content`, `v-list-item-icon`, `v-list-item-avatar`, `v-list-item-action` existieren in Vuetify 3 nicht mehr (dort `prepend`/`append`/`title`-Slots) → Listen-Layout und Slot-Inhalte brechen (u.a. `ImageDetails.vue:60`, `ApplicationsList.vue:106`, `UnifiedSearch.vue:22`). | Auf die Vuetify-3-Slot-Struktur umbauen. |
| M14 | `backend/api/db/schemas/users.py:14` | medium | `password: str` hat keine Längen-/Mindestgrenze. bcrypt schneidet jenseits von 72 Bytes still ab, Passwörter mit gleichem Präfix werden damit akzeptiert. | `Field(min_length=8, max_length=72)`. |

### 19.3 Low — historischer Befundstand

| # | Stelle | Sev | Befund | Fix |
|---|--------|-----|--------|-----|
| L1 | `backend/api/db/crud/settings.py:34` | low | `select(models.SecretKey)` — `models` ist hier `api.db.models.containers`, dort existiert kein `SecretKey` → `AttributeError`. Aktuell ohne Aufrufer (latent, toter Code). | `from api.db.models.settings import SecretKey` benutzen (wie `generate_secret_key`). |
| L2 | `backend/api/routers/setup/setup.py` (Register) | low | `raise HTTPException(400, f"Error creating user: {str(e)}")` gibt rohe DB-/Backend-Fehler an einen UNAUTHENTIFIZIERTEN Aufrufer. | Generische 400-Meldung, Exception nur loggen. |
| L3 | `frontend/src/plugins/notifications.js` | low | Nach dem Vue-3-Rewrite exportiert das Modul Funktionen, wird aber nirgends importiert — Toter Code, solange M11 nicht umgesetzt ist. | Entweder in `main.js` registrieren oder löschen. |
| L4 | `frontend/src/components/compose/ProjectEditor.vue:92` | low | `this.$vuetify.theme.dark` existiert in Vuetify 3 nicht → immer `undefined`, der Ace-Editor nutzt dauerhaft das Twilight-Theme. | `this.$vuetify.theme.global.current.dark`. |

### 19.4 Damals als Falschmeldungen eingestufte Angaben

Diese Punkte wurden vom Hauptagenten geprüft und als **nicht zutreffend** eingestuft:

| Behauptung | Prüfergebnis |
|---|---|
| „`create_key` hat kein `await db.commit()`" | FALSCH — `db/crud/users.py` committet in einem try/except mit Rollback (B26). |
| „`Authorize.is_api_key()` fehlt im containers-Router" | FALSCH — vorhanden in Zeilen 83/123/158/193 plus API-Key-Liveness im WS-Pfad (Zeile 362, B6). |
| „`docker._query_json` existiert nicht, daher ist `prune_resources` kaputt" | FALSCH — `_query_json` ist eine dokumentierte Methode auf `aiodocker.Docker` (Quelle: aiodocker-Doku/Quelltext). Der B16-Fix ist korrekt. |
| „`docker.containers.create(config=…, Cmd=…)` sendet `Cmd` als `Entrypoint`" | FALSCH — `Cmd` im `config`-Dict ist die offizielle, dokumentierte Aufrufweise (aiodocker-Doku-Beispiel). |
| „`update_self_in_background` ohne `name=` erzeugt einen Container-Leak" | FALSCH — der Container hat `AutoRemove: true` und läuft mit `--run-once`; ohne Namen vergibt Docker einen Zufallsnamen. Kein Leck. |
| „`database.py` verdoppelt auch `postgresql+asyncpg://`" | Teilweise falsch — nur der SQLite-Zweig ist betroffen (siehe H9); `postgresql+asyncpg://` bleibt unverändert. |
| „`_host_allowed` lässt den Basishost `example.com` bei `*.example.com` durch" | FALSCH — `endswith(".example.com")` matcht `example.com` gerade NICHT. |
| „`GET /settings/deployment` gehört superuser-gated" | FALSCH — laut eigenem Docstring bewusst für alle authentifizierten Operatoren freigegeben (FND-501 / S7). |
| „`v-slot`-Fix F20 in NetworkDetails ist erledigt" | FALSCH — die Template-Zeile 27 nutzt weiter `router.push` (siehe H7); der damalige Fix traf eine andere Stelle. |

### 19.5 Damalige Reihenfolge (Run R-020)

1. **H1–H4** (kaputte Kernfunktionen: Dashboard-Stats, Container-Aktionen, Update-Prüfung, Listen-Navigation)
2. **H5–H8** (Render-Fehler in Formularen/Import)
3. **H9–H10** (Startup-Crash-Risiko, SMTP-Passwort-Exposition)
4. **M1–M14**, dann **L1–L4**
5. Vor dem Verifizieren der Vuetify-Punkte (M12/M13) `npm ci && npx vite build` laufen lassen.

**Hinweis:** `venv/` und `frontend/node_modules/` waren zum Analysezeitpunkt entfernt
(Speicherplatz-Regel). Vor Fix-Verifikation müssen sie neu errichtet werden:
`python -m venv venv && venv/bin/pip install -r requirements.txt` (backend) bzw.
`npm ci` (frontend).

### 19.6 Historische Restpunkte nach R-020

| Nummer | Stelle | Severity | Rest | Empfehlung |
|---|---|---|---|---|
| M13 | `frontend/src`, 382 Fundstellen | medium | `v-list-item-content`, `v-list-item-icon`, `v-list-item-avatar` und `v-list-item-action` sind Vuetify-2-Elemente und rendern in Vuetify 3 nicht korrekt | Migration auf `prepend`-, `append`- und `title`-Slots in einem eigenen Run, da nur mit Komponententests sicher verifizierbar |
| L3 | `frontend/src/plugins/notifications.js` | low | Modul ist toter Code, weil M11 direkt in `main.js` gelöst wurde | Datei löschen oder in `main.js` registrieren |
| Rest-dense | `frontend/src/components` | low | `dense` und `outlined` auf `v-data-table`, `v-alert`, `v-item-group` und `v-text-field` sind weiterhin Vuetify-2-Reste, außerhalb des Auftrags von R-020 | bei nächster UI-Berührung auf `density` und `variant` umstellen |
| Rest-status | `backend/api/actions/apps.py` Zeilen 358 und 369 | low | dort steht noch ein `getattr`-Aufruf statt `safe_http_status`, dadurch ist der Sentinel 900 möglich | auf `safe_http_status` umstellen |
| Rest-pwd | `backend/api/routers/auth_2fa.py` Zeile 131 | low | Feld `password` ohne Byte-Obergrenze, ein Wert über 72 Byte liefe in bcrypt, praktisch unerreichbar | optional `field_validator` wie in `schemas/users.py` |

---

## Run-Protokoll

Kurzgedächtnis des Projekts, welcher Run was geändert hat; neueste zuerst; wird bei jedem Run ergänzt und nie umgeschrieben; Details stehen im jeweiligen Commit und in der `CHANGELOG.md`.

| Run | Datum | Commit | Kernänderung | Tests (Backend/Frontend) |
|---|---|---|---|---|
| R-022 | 2026-10-02 | 0ea2d63; Remote-Integration derselben Lieferung | Credential-Versionen, CSRF/TOTP/SMTP, Docker/Compose/Template- und Vue-Korrekturen; Kandidat 3.0.1, Docker-Prüfung offen | vor Integration 852/197; zusätzlich 42 Policy-Tests; finale Merge-Belege im Behebungsbericht |
| R-021 | 2026-09-10 | Doku-Sync-Commit | Doku-Sync: Run-Protokoll und CHANGELOG-Pflichtregel, Status Abschnitt 18, Baseline von 513 auf 543 | 543/21 |
| R-020 | 2026-09-10 | aed5e1f | Audit-Befunde Abschnitt 18 behoben, H1 bis H10, M1 bis M14, L1 bis L4, Backend und Frontend | 543/21 |
| R-019 | 2026-09-08 | 5924edc | Kosmetik-Rest: F72 Race-Guard, B30 WS-Close-Frame, F41 bis F50, F59 bis F70 | 539/21 |
| R-018 | 2026-09-08 | 55636b8 | B14: Self-Restart mit eigenem aiodocker-Client plus drei Tests | 539/21 |
| R-017 | 2026-09-08 | 84d5f09 | Rest-Batch: F16 vee-validate v4, F34 bis F39, F56, F68, F69, F73, F77, B26 bis B28 | 536/21 |
| R-016 | 2026-09-08 | 627fe0d | B22 Last-Admin-Update-Gate, F33 Port-Links protokollbewusst, F71 noopener | 536/21 |
| R-015 | 2026-09-07 | 41a4750 | TOTP valid_window gleich eins, CI-Flakiness an der Fenstergrenze behoben | 536/21 |
| R-014 | 2026-09-07 | e5214b6 | Subagenten-Bug-Batch B1 bis B24 und F1 bis F78, plus Analyse in Abschnitt 18 | 536/21 |
| R-013 | 2026-09-03 | 7e1808c | Dockerfile: COPY der Wheels vor pip install, CI-Build wieder grün | CI grün |
| R-012 | 2026-09-03 | 4f8a063 | P0/P1-Security-Fixes und P2-Verbesserungen, Backend und Frontend | 536/21 |
| R-011 | 2026-08-21 | e5443dc | Doku: Docker-Socket-Proxy Least-Privilege-Matrix, N-01 und N-02 | keine |
| R-010 | 2026-08-21 | 3091545 | B-07: Leader-Lock für Watchtower plus Test | keine |
| R-009 | 2026-08-21 | a46a412 | N-13: SMTP Rate-Limit und Debounce für Test-Mail plus Tests | keine |
| R-008 | 2026-08-21 | 5b90f0b | B-09: API-Keys erfordern aktiven APIKEY-Datensatz plus Tests | keine |
| R-007 | 2026-08-21 | 5671807 | N-11: timezone-aware DateTime und Alembic env.py repariert | keine |
| R-006 | 2026-08-21 | ac1134f | N-12: request.client gleich None sicher behandelt | keine |
| R-005 | 2026-08-21 | 6588add | N-09: Token-Ablauf auf ACCESS_TOKEN_EXPIRE_MINUTES konsolidiert | keine |
| R-004 | 2026-08-21 | 1d1c0a2 | N-06: race-sichere SECRET_KEY-Erzeugung plus Multiprozess-Test | keine |
| R-003 | 2026-08-21 | 06f317f | Test-Import normalize_username korrigiert | keine |
| R-002 | 2026-08-21 | a72f5ba | P1: B-05 Docker CLI und Compose, B-08 slowapi, B-13 Login-Auth | keine |
| R-001 | 2026-08-21 | bfbc1c2 | Tests und Specs in git aufgenommen | keine |

**Hinweis:** die Spalte Tests nennt den Stand am Ende des Runs; `keine` bedeutet, dass in diesem Run keine Suiten liefen; exakte Uhrzeiten stehen in der `CHANGELOG.md`.
