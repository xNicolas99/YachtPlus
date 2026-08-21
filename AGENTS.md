# AGENTS.md — orientation for coding agents

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
| Frontend | Vue 3.4 + Vite 7 + Vuetify 3, Vuex 4 for state + Pinia 3 mounted (active), vue-router 4, vee-validate v4, axios. Routes are lazy-loaded (code-split); vendor libs split via `manualChunks` in `vite.config.js`. |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.x (async engine), aiodocker, APScheduler, slowapi (rate limit), bcrypt, PyJWT, pyotp |
| DB | SQLite default (`sqlite:////config/yacht.db`, via `sqlite+aiosqlite`); Postgres via `postgresql+asyncpg`; MySQL via `mysql+aiomysql` — all driven by `DATABASE_URL` |
| Build/Deploy | Multi-stage `Dockerfile` (Node build → Python deps build → Python runtime + nginx); `docker-compose.yml`; GitHub Actions in `.github/workflows/` (`docker-image.yml`, `ghcr.yml`, `ci.yml`) |
| Test | pytest (backend), vitest (frontend) | Backend and frontend tests are **tracked** in this repo (`backend/tests/`, `frontend/**/*.test.js`). CI runs both suites. |

---

## 3. Layout (read this before adding files)

```
backend/
  start.sh                 # Entrypoint inside the Docker image (sets perms, exec gunicorn+nginx)
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
    services/              # Background jobs (watchtower poll, audit cleanup)
    utils/                 # Pure helpers: compose parsing, crypto, audit, sanitiser
  alembic/                 # Migrations
  tests/                   # pytest, with conftest.py for env setup (tracked; run in CI)
  alembic/versions/        # tracked Alembic migrations; run `alembic upgrade head` for upgrades
  requirements.txt
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
    utils/                 # Pure JS helpers + their vitest specs
  vite.config.js
  package.json
scripts/
  push-to-github.sh        # Push local work to GitHub with a PAT (see scripts/README.md)
  README.md
Dockerfile
docker-compose.yml         # Minimal production example
docker-compose.example.yml # Hardened example using a docker-socket-proxy
nginx.conf
fail2ban/                  # jail.local + filter for fail2ban-style brute-force protection
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
                        │     1. check_setup_status   → 428 if setup not finalized (async DB)
                        │     2. CORSMiddleware        → uses settings.CORS_ORIGINS
                        │     3. _trusted_host_middleware (custom) → uses settings.ALLOWED_HOSTS
                        │     4. add_security_headers  → CSP, etc.
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
  HttpOnly cookie `access_token_cookie`. `secure=True` when
  `ENVIRONMENT=production`. SameSite=lax.
- **Claims:** `sub` (username), `exp`, optional `setup_pending: bool`.
- **Two cookie-issuing endpoints:**
  - `POST /api/auth/login_cookie` — normal login, validates password + TOTP
    if 2FA enabled.
  - `POST /api/setup/register` — first-time admin registration. Issues a
    *15-minute* token with `setup_pending=True`. Body returns only
    `{login, username}`, **never** the raw token.
- **Refresh:** axios interceptor in `main.js` catches 401 → POSTs
  `/api/auth/refresh` (CSRF token in header) → retries the original call.

### Two defense layers, both must stay intact

1. **Middleware** (`backend/api/main.py`, `check_setup_status`): returns
   `428 Precondition Required` on any `/api/*` route except `/api/auth`
   and `/api/setup` until `is_setup_completed(db) == True`.
2. **`auth_check`** (`backend/api/auth/auth.py`): rejects tokens with
   `setup_pending=True` (403). Used by every data router.
   **`auth_check_setup_pending`** allows them — but *only while setup is
   not yet finalized* (stale-token block).

### /refresh validates the underlying account

`POST /api/auth/refresh` is not just a token-restamper: it calls
`auth_check`, looks the user up in the DB, and rejects when the user is
missing or `is_active == False`. A deactivated account therefore cannot
keep extending its session until the original token's `exp`. On rejection
the cookie is cleared so the SPA's interceptor falls through to the
`/login` redirect.

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
| `/api/compose/{project}/edit` | `auth_check` + `perm_restart` — editing a compose file changes how the stack restarts |
| `/api/compose/{project}/support` | superuser only |
| `/api/templates` POST / DELETE / `/refresh` | superuser only via local `_require_superuser` helper (mutates the shared library + outbound URL fetch) |
| `/api/containers/{id}/exec` (WS) | shell-name whitelist → JWT decode → reject `setup_pending` → DB lookup (`is_active`) → `perm_start`. See section 5 below for the WS-specific contract. |
| `/api/auth/users/{user_id}` DELETE | superuser only; refuses self-delete and refuses to zero out the superuser table |
| `/api/auth/api/keys/{id}` DELETE | owner OR superuser; non-owner gets the same "Key not found" payload as a missing id (no IDOR id-existence leak) |

### `/api/containers/{id}/exec` WebSocket contract

1. `await websocket.accept()` — required to receive a `send_json`/`close` frame.
2. **Shell-name whitelist** (`containers.py::ALLOWED_EXEC_SHELLS`). Anything
   else gets a `{"error": "Forbidden: shell not allowed"}` and a 1008 close
   *before* any auth check, so token-probing attempts get no signal.
3. Cookie-only JWT (`access_token_cookie`); URL/query tokens never accepted.
4. Reject `setup_pending` tokens, reject unknown / inactive users, reject
   anything without `perm_start` (superusers bypass).
5. Only then open the `aiodocker.Docker(...)` and stream.

Terminal IN/OUT bytes are deliberately not logged — they include passwords
typed at sudo prompts, tokens echoed by tools, file contents dumped by
`cat`. The debug log captures frame length only.

---

## 6. Security defaults (don't loosen without thinking)

| Defense | Where | Notes |
|---|---|---|
| HttpOnly auth cookie | `api/auth/jwt.py: set_access_cookies` | JS cannot read the token. |
| CSP | `api/main.py` `add_security_headers` | `script-src 'self' 'unsafe-inline'`. **No `unsafe-eval`** — keep it that way. |
| Trusted-host | `api/main.py` `_trusted_host_middleware` (custom, not Starlette's) | Reads `settings.ALLOWED_HOSTS`. Override with `YACHT_ALLOWED_HOSTS=…`. Rejects non-matching Host headers with 400. |
| CORS allowlist | `api/main.py` `CORSMiddleware` | Reads `settings.CORS_ORIGINS`. Override with `YACHT_CORS_ORIGINS=…`. Startup fails fast if list contains `*` (incompatible with `allow_credentials=True`) or an entry without a scheme. |
| HTML sanitisation | `frontend/src/main.js` `$sanitize` | DOMPurify with explicit allowlist; covers all `v-html` sites. |
| Per-IP login limit | `api/routers/users.py` `@limiter.limit("5/minute")` | slowapi on login + refresh + key-creation. |
| Per-IP fail2ban | `api/utils/security.py: check_ip_restriction` | 5 failed logins / 15 min from the same IP → 403. |
| Per-username lockout | same | 20 failed logins / 30 min for the same username (across IPs) → 403. Error wording is identical to the IP block so an attacker can't tell which guard fired. |
| Rate-limiting | `api/utils/security.py: limiter` | slowapi shared instance with key function `_resolve_client_ip`. Default limit 100/minute; Docker/compose/resource mutations limited to 10–60/minute by endpoint. Tests disable the decorator at import time so unit tests calling handlers directly still run. |
| Trusted-proxy allowlist | `api/utils/security.py: _is_trusted_proxy` | X-Real-IP / X-Forwarded-For are **only** honoured when the direct peer is in `settings.TRUSTED_PROXIES` (`YACHT_TRUSTED_PROXIES=ip[,cidr,...]`). Default empty → never trust them. Stops same-LAN attackers from spoofing client-IP attribution. |
| API-key delete | `api/routers/users.py: delete_api_key` | DELETE verb (GET kept as deprecated alias). Ownership-or-superuser check in `crud.blacklist_api_key`; non-owner gets the same "not found" payload as a missing id (no IDOR leak). |
| API-key creation rate limit | `api/routers/users.py: create_api_key` | `@limiter.limit("5/minute")` — keys are long-lived (10y exp). |
| SECRET_KEY | `api/settings.py` `get_or_create_secret_key` | Reads env, otherwise persists to `SECRET_KEY_FILE`. **Fail-fast** if neither possible — no ephemeral fallback. |
| At-rest crypto | `api/utils/crypto.py` | PBKDF2-HMAC-SHA256 (600k iterations, 16-byte salt persisted at `FERNET_SALT_FILE`, default `/config/.fernet_salt`). v2 tokens are prefixed `v2:`; legacy v1 (single-SHA256, no salt) tokens stay decryptable so existing 2FA seeds aren't invalidated. New writes always emit v2 → lazy migration. |
| 2FA enforcement | `api/routers/setup/setup.py: finalize_setup` | Setup cannot complete without 2FA enabled. |
| WS auth (exec) | `api/routers/containers.py` | Cookie-only handshake, never URL/query token. Shell-name whitelist → reject setup_pending → DB lookup → `perm_start` gate. See section 5 for the full chain. |
| Template SSRF mitigation | `api/db/crud/templates.py` `validate_url` + `SafeRedirectHandler` | Catches `gaierror`/`herror`/`timeout`/generic `OSError`, rejects empty resolutions, blocks all private-range IPs **including on every redirect**. Fetch timeout `TEMPLATE_FETCH_TIMEOUT_S = 15`. Reuse this pattern for any user-supplied URL fetch. |
| Last-admin guard | `api/routers/users.py: delete_user` | Refuses self-deletion and refuses to leave zero superusers in the table. |

---

## 7. External integrations

| Integration | How | Env |
|---|---|---|
| Docker daemon (async) | `aiodocker.Docker(url=settings.DOCKER_HOST)` | `DOCKER_HOST`, `DOCKER_GID` |
| Docker daemon (sync) | `api.utils.docker_client.get_sync_docker_client()` — wraps `docker.DockerClient(base_url=...)` when `settings.DOCKER_HOST` is set, else `docker.from_env()`. **Never call `docker.from_env()` directly** — it bypasses an operator-configured TCP proxy. | `DOCKER_HOST` |

#### Least-privilege Docker socket proxy matrix (N-01/N-02)

When YachtPlus talks to Docker through a socket proxy (e.g. `tecspirit/docker-socket-proxy`),
the proxy should allow only the API paths the backend actually uses. The matrix below is the
authoritative reference; keep it in sync with any new Docker call.

| Area | Proxy env flags needed | YachtPlus usage |
|---|---|---|
| Read resources | `CONTAINERS=1`, `IMAGES=1`, `NETWORKS=1`, `VOLUMES=1` | Dashboard stats, app list, resource lists, logs, inspect |
| Container lifecycle | `POST=1` + `CONTAINERS_CREATE=1`, `CONTAINERS_UPDATE=1`, `CONTAINERS_DELETE=1` | start / stop / restart / recreate / remove containers |
| Image management | `IMAGES_CREATE=1`, `IMAGES_DELETE=1` | pull / prune / remove images |
| Network management | `NETWORKS_CREATE=1`, `NETWORKS_DELETE=1` | create / remove networks |
| Volume management | `VOLUMES_CREATE=1`, `VOLUMES_DELETE=1` | create / remove volumes |
| Exec (terminal) | `POST=1` + `CONTAINERS_UPDATE=1` | `/api/containers/{id}/exec` WebSocket |
| Compose | depends on above flags | `docker compose` CLI still runs inside the YachtPlus container; the proxy only filters the direct daemon calls |

The production `docker-compose.example.yml` ships with a read-only proxy mount
(`/var/run/docker.sock:ro`) and explicit allowlist. Direct `/var/run/docker.sock`
mounts should never be used in production because a compromised YachtPlus container
can gain root on the host through the unfiltered Docker API.
| docker-compose CLI | `subprocess.run` inside `_run_compose_command` (array form, no `shell=True`). Subcommand is whitelisted twice: at the router and again at `_compose_action_sync` / `_compose_app_action_sync` via `_ALLOWED_PROJECT_ACTIONS` / `_ALLOWED_APP_ACTIONS`. Sync, run in thread pool via `run_in_thread`. | `COMPOSE_DIR` |
| Docker Hub / GHCR | Plain HTTP for image metadata + image listing | — |
| Template registries | URL fetch via `urllib` + `SafeRedirectHandler`, hard timeout `TEMPLATE_FETCH_TIMEOUT_S`. SSRF-validated on every redirect. | — |
| Email (SMTP) | Stored credentials in DB, encrypted via `utils/crypto` (PBKDF2 v2 with legacy v1 fallback) | — |

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
  `await run_in_thread(...)` (array-form `subprocess.run`, no `shell=True`).
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

### Known intentionally-sync exceptions (documented)

- `api/utils/audit.py` `log_activity` is sync (`db.add`/`db.commit`); async
  routers call it via `asyncio.to_thread`. Kept sync to avoid threading
  concerns in the audit path.
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
- **Global snackbar.** `App.vue` mounts `components/notifications/snackbar.vue`
  once. Views push feedback via the `snackbar` Vuex module (`setErr`/`setSuccess`/
  `setMessage`) instead of `console.log`. The component uses Vuetify 3 `v-model`
  + `location` (not the Vuetify 2 `:value`/`:bottom`).
- **Theme.** `components/serverSettings/Theme.vue` uses the Vuetify 3 `useTheme`
  refs (`$vuetify.theme.global.name.value`). Persists `dark_theme`,
  `theme_primary`, `theme_secondary` in `localStorage`. `App.vue` restores the
  theme on mount.
- **Dashboard polling.** `views/Home.vue` polls only while the tab is visible
  (`document.hidden` guard) and refreshes immediately on `visibilitychange`.
  Keep this pattern for any new auto-refresh view.
- **Vuetify 3 syntax.** Use `v-model`, `location`, `density`, `variant`,
  `v-icon start/end`, `v-tooltip location` — not the Vuetify 2 `:value`,
  `bottom`, `dense`, `outlined`, `dark`, `v-icon left/right`, `v-tooltip bottom`
  forms. `v-tabs-items`/`v-tab-item` are `v-window`/`v-window-item` in v3.
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
pip install -r requirements.txt
# On Windows: uvloop has no wheels. Skip it:
#   grep -v '^uvloop' requirements.txt > /tmp/req && pip install -r /tmp/req

export DATABASE_URL="sqlite:///./local.db"   # avoid /config/yacht.db
uvicorn api.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
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

Current baseline: **513 backend + 21 frontend tests, all green.**

`backend/tests/conftest.py` also provides shared async `db` / `db_session`
fixtures (in-memory `sqlite+aiosqlite`, `StaticPool`). After the async
migration, every test that touches the DB uses an `AsyncSession`;
`MockAuth`-style classes in tests have `async def jwt_required()` /
`async def get_jwt_subject()`.

---

## 10. Database / migrations

- Models in `backend/api/db/models/`. Adding a column? Add it to the model
  and create an Alembic revision in `backend/alembic/versions/`.
- `Base.metadata.create_all(bind=engine)` runs at app startup, which is
  enough for SQLite + fresh installs. For real upgrades use
  `alembic upgrade head`.
- The `User` model encrypts `otp_secret` at rest via `api.utils.crypto`.
  Don't write the plain TOTP secret to the DB.

---

## 11. Configuration (env vars)

| Var | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | — | JWT signing key. If unset, derived from `SECRET_KEY_FILE`. |
| `SECRET_KEY_FILE` | `/config/.secret_key` | Where the key is persisted if `SECRET_KEY` is unset. Must be writable. |
| `FERNET_SALT_FILE` | `/config/.fernet_salt` | Where the at-rest crypto salt is persisted. 16 bytes, generated once on first start. Falls back to `.fernet_salt` in cwd if `/config` doesn't exist. |
| `ENVIRONMENT` | `development` | When `production`, cookies get `Secure` flag. |
| `SECURE_COOKIES` | derived | Force-override cookie Secure flag. |
| `DATABASE_URL` | `sqlite:////config/yacht.db` | SQLAlchemy URL. |
| `YACHT_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | TrustedHostMiddleware list. |
| `YACHT_CORS_ORIGINS` | localhost variants | CORS origin list. Startup fails fast if it contains `*` or an entry without scheme. |
| `YACHT_TRUSTED_PROXIES` | `127.0.0.1,::1` | Comma-separated IPs / CIDRs whose `X-Real-IP` / `X-Forwarded-For` headers we honour. Default `["127.0.0.1", "::1"]` (loopback). Set to your reverse proxy's IP when running behind nginx / Traefik. |
| `COMPOSE_DIR` | `/compose/` | Where compose project subdirectories live. Trailing slash is part of the contract — every call site does `settings.COMPOSE_DIR + name`. |
| `DOCKER_HOST` | (unset → SDK default = `/var/run/docker.sock`) | Docker connection. Declared as `Optional[str]` on Settings; when set, **both** the async (`aiodocker`) and sync (`utils/docker_client`) paths honour it. |
| `DOCKER_GID` | autodetect | Set if you hit socket permission errors. |
| `DISABLE_AUTH` | `False` | **Dev only.** Bypasses every auth check. Never set in prod. |

---

## 12. High-risk areas — extra caution required

| Area | Why | Required action before merging |
|---|---|---|
| Anything in `api/auth/` or `api/routers/setup/` | One broken assertion = auth bypass | Add or extend a pytest case in `tests/test_auth*.py` or `test_setup.py`. Run the full setup flow manually if behaviour changes. |
| Adding a new `/api/*` route | Default is "blocked by middleware" | Decide consciously: data route (`auth_check`) vs setup route (`auth_check_setup_pending`) vs public (whitelist in middleware). |
| Container logs | Logs often contain secrets / tokens | `get_container_logs` requires `auth_check` **and** `check_permission("perm_start", Authorize, db)`. |
| Returning docker/subprocess errors to the client | Information disclosure: daemon paths, hostnames, env values, possibly secrets | Use `api.utils.error_handler.docker_error_detail()` for aiodocker exceptions and generic messages for compose/subprocess failures. Log full details server-side. |
| User-supplied URL fetched server-side | SSRF risk | Use `validate_url` + `SafeRedirectHandler` (`api/db/crud/templates.py`). It rejects private-range IPs on every redirect and on every socket-error mode (gaierror, herror, timeout, OSError, empty resolution). Always pass `timeout=` to the opener. |
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

- **`/config` doesn't exist outside Docker.** Override `DATABASE_URL` and
  `SECRET_KEY_FILE` for local dev or the app refuses to start.
- **`uvloop` doesn't build on Windows.** Filter it out of `requirements.txt`
  for local Windows dev. The Docker image is Linux so it's fine there.
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

## 16. Backwards-compatibility carve-outs

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

## 17. Notes & journals

`.Jules/` holds free-form journal files from past agent runs
(`palette.md`, `sentinel.md`, `mechanic.md`, `bolt.md`). They are reference
notes, not policy. Read them if you want historical context; don't treat
them as ground truth — verify against current code.

Past audit reports (`AUDIT_REPORT_*.md`, `SECURITY_AUDIT_REPORT_2025.md`,
`migration_plan.md`) have been removed as they described long-resolved
states and contained inaccuracies. The README + this file are the
authoritative orientation now.
