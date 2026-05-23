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
| Frontend | Vue 3.4 + Vite 5 + Vuetify 3, Vuex 4 for state, Pinia bootstrap present but no Pinia store currently, vue-router 4, vee-validate v4, axios |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.x, aiodocker, APScheduler, slowapi (rate limit), bcrypt, PyJWT, pyotp |
| DB | SQLite default (`sqlite:////config/yacht.db`); Postgres / MySQL via `DATABASE_URL` |
| Build/Deploy | Multi-stage `Dockerfile` (Node build → Python runtime + nginx); `docker-compose.yml`; GitHub Actions in `.github/workflows/` (`docker-image.yml`, `ghcr.yml`) |
| Test | pytest (backend, 338 tests), vitest (frontend, 16 tests), Playwright dev-dep present but no active suite |

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
  tests/                   # pytest, with conftest.py for env setup
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
                        │     1. check_setup_status   → 428 if setup not finalized
                        │     2. CORSMiddleware        → uses settings.CORS_ORIGINS
                        │     3. TrustedHostMiddleware → uses settings.ALLOWED_HOSTS
                        │     4. add_security_headers  → CSP, etc.
                        │                              │
                        │                              ▼
                        │   Router → Endpoint
                        │     - Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
                        │     - auth_check(Authorize)              # data routes
                        │       OR auth_check_setup_pending(Authorize, db)  # setup/2FA
                        │     - check_permission("perm_x", Authorize, db)  # for fine-grained
                        │     - business call → actions/* or db/crud/*
                        │
                        └─► /     ─► static SPA (frontend/dist via nginx)
```

Same-origin model: SPA and API share the host, so the HttpOnly auth cookie
flows automatically. The frontend never sees the raw JWT.

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
  `auth_check_setup_pending(Authorize, db)`.
- **Normal data routes:** call `auth_check(Authorize)` first thing in the
  handler. Optionally follow with `check_permission("perm_x", Authorize, db)`
  for non-superuser access control.

### User model permissions (in `db/models/users.py`)

Flat boolean flags on `User`: `is_superuser`, `is_active`, `is_2fa_enabled`,
and granular `perm_start`, `perm_stop`, `perm_restart`, `perm_delete`.
Superusers bypass `check_permission`.

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
| Trusted-host | `api/main.py` `TrustedHostMiddleware` | Reads `settings.ALLOWED_HOSTS`. Override with `YACHT_ALLOWED_HOSTS=…`. |
| CORS allowlist | `api/main.py` `CORSMiddleware` | Reads `settings.CORS_ORIGINS`. Override with `YACHT_CORS_ORIGINS=…`. Startup fails fast if list contains `*` (incompatible with `allow_credentials=True`) or an entry without a scheme. |
| HTML sanitisation | `frontend/src/main.js` `$sanitize` | DOMPurify with explicit allowlist; covers all `v-html` sites. |
| Per-IP login limit | `api/routers/users.py` `@limiter.limit("5/minute")` | slowapi on login + refresh + key-creation. |
| Per-IP fail2ban | `api/utils/security.py: check_ip_restriction` | 5 failed logins / 15 min from the same IP → 403. |
| Per-username lockout | same | 20 failed logins / 30 min for the same username (across IPs) → 403. Error wording is identical to the IP block so an attacker can't tell which guard fired. |
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

**Comments:** the codebase has a lot of historical inline commentary (decisions,
abandoned approaches, ASCII trace logs). When you touch a function, prune the
stale comments along the way — don't add to the pile.

**Error envelope:** all API errors return `{"detail": "..."}` (FastAPI default).
Frontend reads `err.response?.data?.detail` and surfaces it via `snackbar/setErr`.

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

```bash
# Backend
cd backend
DATABASE_URL="sqlite:///./test.db" python -m pytest tests/

# Frontend
cd frontend
npx vitest run
```

Current baseline: **338 backend + 16 frontend tests, all green.**
`backend/tests/conftest.py` injects `YACHT_ALLOWED_HOSTS=...,testserver`
*before* `Settings` is evaluated — needed because `TrustedHostMiddleware`
would otherwise reject TestClient's default `Host: testserver`.

`tests/test_cors.py` and `tests/test_setup.py` are excluded from the
default run via `--ignore=` because they try to open `/config/yacht.db`
at collection time, which doesn't exist outside the Docker image. Fix
them or set `DATABASE_URL` if you need them.

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
| `YACHT_TRUSTED_PROXIES` | (empty) | Comma-separated IPs / CIDRs whose `X-Real-IP` / `X-Forwarded-For` headers we honour. Default empty → never trust them; client IP attribution uses the direct peer. Set to your reverse proxy's IP when running behind nginx / Traefik. |
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
| User-supplied URL fetched server-side | SSRF risk | Use `validate_url` + `SafeRedirectHandler` (`api/db/crud/templates.py`). It rejects private-range IPs on every redirect and on every socket-error mode (gaierror, herror, timeout, OSError, empty resolution). Always pass `timeout=` to the opener. |
| Subprocess / shell invocation | Command injection | No `shell=True`. Pass args as a list. Validate every component if it came from request data. Subcommand whitelist at the action layer too, not just the router (see `_ALLOWED_PROJECT_ACTIONS`). |
| Adding a query/path arg that becomes a subprocess token, exec command, or shell binary | Same | Whitelist at both router and action layer. Reject before any auth check if the value is suspicious — keeps token-probing attempts from getting any signal. The container-exec WS `shell` param is the canonical example. |
| Touching the cookie name, `setup_pending`, or `is_active` semantics | Frontend depends on the exact strings/shape | grep both backend and frontend for the symbol before changing. |
| Removing `unsafe-eval` from CSP is a non-goal — it's already removed. Adding it back is a no. | XSS surface | If a dep needs `unsafe-eval`, the dep is the problem. |
| Adding `settings.X` reference for a new env var | Pydantic uses `extra='forbid'` | Declare `X` as a field on the `Settings` class in `api/settings.py`. Otherwise the read crashes with `AttributeError` at request time. `tests/test_settings_fields.py` pins the must-exist contract for the currently-declared fields. |
| Calling `docker.from_env()` | Bypasses `settings.DOCKER_HOST` | Always go through `api.utils.docker_client.get_sync_docker_client()` for the sync SDK. |
| Trusting `X-Real-IP` / `X-Forwarded-For` outside `_resolve_client_ip` | IP-spoofing for rate-limit evasion | Don't. There's one entry point and it requires the peer to be in `settings.TRUSTED_PROXIES`. |
| Logging shell input/output, terminal frames, JWTs, or DB rows containing secrets | Sensitive data in logs | Log lengths, ids, or sanitised summaries — never the raw bytes. Semgrep's log-leak rule is configured to flag this. |

---

## 13. Common gotchas

- **`/config` doesn't exist outside Docker.** Override `DATABASE_URL` and
  `SECRET_KEY_FILE` for local dev or the app refuses to start.
- **`uvloop` doesn't build on Windows.** Filter it out of `requirements.txt`
  for local Windows dev. The Docker image is Linux so it's fine there.
- **Two setup flag sources:** `is_setup_completed(db)` checks both the
  `SetupStatus` table *and* the legacy `/config/.setup_completed` file. If
  you reset state, kill both.
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
- **`settings.X` for an unknown field crashes.** Pydantic v2 + `extra='forbid'`
  means *only declared fields* exist. If a previous patch added a code
  reference but forgot the field declaration, the line bombs at runtime
  with `AttributeError` instead of e.g. returning `None`. Add the field.
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
