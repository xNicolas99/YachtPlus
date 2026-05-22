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
| Test | pytest (backend, 213 tests), vitest (frontend, 9 tests), Playwright dev-dep present but no active suite |

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

---

## 6. Security defaults (don't loosen without thinking)

| Defense | Where | Notes |
|---|---|---|
| HttpOnly auth cookie | `api/auth/jwt.py: set_access_cookies` | JS cannot read the token. |
| CSP | `api/main.py` `add_security_headers` | `script-src 'self' 'unsafe-inline'`. **No `unsafe-eval`** — keep it that way. |
| Trusted-host | `api/main.py` `TrustedHostMiddleware` | Reads `settings.ALLOWED_HOSTS`. Override with `YACHT_ALLOWED_HOSTS=…`. |
| CORS allowlist | `api/main.py` `CORSMiddleware` | Reads `settings.CORS_ORIGINS`. Override with `YACHT_CORS_ORIGINS=…`. |
| HTML sanitisation | `frontend/src/main.js` `$sanitize` | DOMPurify with explicit allowlist; covers all `v-html` sites. |
| Rate limit on login | `api/routers/users.py` `@limiter.limit("5/minute")` | slowapi; also tracks per-IP login attempts in DB for fail2ban-style block. |
| SECRET_KEY | `api/settings.py` `get_or_create_secret_key` | Reads env, otherwise persists to `SECRET_KEY_FILE`. **Fail-fast** if neither possible — no ephemeral fallback. |
| 2FA enforcement | `api/routers/setup/setup.py: finalize_setup` | Setup cannot complete without 2FA enabled. |
| WS auth | `api/routers/containers.py` | Reads cookie directly off WS handshake; never accepts token via URL/query. |
| Template SSRF mitigation | `api/db/crud/templates.py` `SafeRedirectHandler` | Reuse this pattern for any user-supplied URL fetch. |

---

## 7. External integrations

| Integration | How | Env |
|---|---|---|
| Docker daemon | `aiodocker` (async) and `docker` SDK (sync, wrapped in `loop.run_in_executor`) | `DOCKER_HOST`, `DOCKER_GID` |
| docker-compose CLI | `subprocess.run` inside `_run_compose_command` (sync, run in thread pool via `run_in_thread`) | — |
| Docker Hub / GHCR | Plain HTTP for image metadata + image listing | — |
| Template registries | URL fetch via `urllib` + `SafeRedirectHandler` | — |
| Email (SMTP) | Stored credentials in DB, encrypted via `utils/crypto` | — |

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

Current baseline: **213 backend + 9 frontend tests, all green.**
`backend/tests/conftest.py` injects `YACHT_ALLOWED_HOSTS=...,testserver`
*before* `Settings` is evaluated — needed because `TrustedHostMiddleware`
would otherwise reject TestClient's default `Host: testserver`.

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
| `ENVIRONMENT` | `development` | When `production`, cookies get `Secure` flag. |
| `SECURE_COOKIES` | derived | Force-override cookie Secure flag. |
| `DATABASE_URL` | `sqlite:////config/yacht.db` | SQLAlchemy URL. |
| `YACHT_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | TrustedHostMiddleware list. |
| `YACHT_CORS_ORIGINS` | localhost variants | CORS origin list. |
| `DOCKER_HOST` | `unix:///var/run/docker.sock` | Docker connection. |
| `DOCKER_GID` | autodetect | Set if you hit socket permission errors. |
| `DISABLE_AUTH` | `False` | **Dev only.** Bypasses every auth check. Never set in prod. |

---

## 12. High-risk areas — extra caution required

| Area | Why | Required action before merging |
|---|---|---|
| Anything in `api/auth/` or `api/routers/setup/` | One broken assertion = auth bypass | Add or extend a pytest case in `tests/test_auth*.py` or `test_setup.py`. Run the full setup flow manually if behaviour changes. |
| Adding a new `/api/*` route | Default is "blocked by middleware" | Decide consciously: data route (`auth_check`) vs setup route (`auth_check_setup_pending`) vs public (whitelist in middleware). |
| User-supplied URL fetched server-side | SSRF risk | Use `SafeRedirectHandler` (`api/db/crud/templates.py`) or equivalent. Reject private-range IPs. |
| Subprocess / shell invocation | Command injection | No `shell=True`. Pass args as a list. Validate every component if it came from request data. |
| Touching the cookie name, `setup_pending`, or `is_active` semantics | Frontend depends on the exact strings/shape | grep both backend and frontend for the symbol before changing. |
| Removing `unsafe-eval` from CSP is a non-goal — it's already removed. Adding it back is a no. | XSS surface | If a dep needs `unsafe-eval`, the dep is the problem. |

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
