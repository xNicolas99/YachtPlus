# YachtPlus

YachtPlus is a self-hosted container management UI for Docker and Docker Compose. It focuses on 1‑click template deployments while keeping the security defaults sane for self-hosting scenarios.

---

## Tech stack

| Layer | Stack |
|---|---|
| Frontend | Vue 3.4, Vite 5, Vuetify 3, Pinia + Vuex 4, vee-validate v4 |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, aiodocker, APScheduler |
| Auth | JWT in HttpOnly cookies, mandatory 2FA (TOTP), bcrypt password hashing, slowapi rate limiting |
| Storage | SQLite by default (`/config/yacht.db`), Postgres/MySQL supported via `DATABASE_URL` |
| Packaging | Single Docker image, frontend built with Vite, served via nginx, FastAPI behind gunicorn |

---

## Architecture in one minute

```
Browser ──► nginx (port 8080) ──► /api/*  ──► gunicorn (FastAPI, /api)
                              └──► /        ──► static SPA from frontend/dist

FastAPI ──► aiodocker  ──► /var/run/docker.sock
        ──► SQLAlchemy ──► /config/yacht.db (default)
        ──► APScheduler (background jobs: watchtower polling, audit cleanup)
```

The container ships **one** image with both frontend and backend. nginx routes API traffic to gunicorn and static traffic to the built SPA. The frontend talks to the API over same-origin so the HttpOnly auth cookie is sent automatically.

---

## Auth & setup flow

The first launch is intentionally locked down:

1. **`GET /api/setup/status`** — frontend checks if first-time setup is required.
2. **`POST /api/setup/register`** — creates the first admin user with `is_active=False`, issues a short-lived JWT (15 min) with the `setup_pending=True` claim inside an HttpOnly cookie. Body returns only `{login, username}`, never the token.
3. **`POST /api/auth/2fa/generate`** + **`POST /api/auth/2fa/enable`** — admin scans the TOTP QR and confirms a 6-digit code. These endpoints accept `setup_pending=True` tokens but only while setup is incomplete.
4. **`POST /api/setup/finalize`** — verifies 2FA is enabled, flips `is_active=True`, marks setup complete, and issues a fresh token without `setup_pending`.

Two defense layers ensure a `setup_pending=True` token can't touch user data:

- **`check_setup_status` middleware** (`backend/api/main.py`): returns `428 Precondition Required` on any `/api/*` route except `/api/auth` and `/api/setup` until setup is finalized.
- **`auth_check` dependency** (`backend/api/auth/auth.py`): rejects `setup_pending=True` tokens with `403 "Setup is pending, restricted access"`. Used by every data router.

Subsequent logins go through **`POST /api/auth/login_cookie`**, which validates credentials, requires the TOTP code, and sets the HttpOnly cookie. The frontend never sees the raw JWT — it stays in the cookie jar and is sent automatically with every API call.

WebSocket exec sessions (container terminal) reuse the same cookie: `backend/api/routers/containers.py` reads `access_token_cookie` straight off the WS handshake; no token is ever passed in the URL.

---

## Security defaults

| Defense | Where | Notes |
|---|---|---|
| HttpOnly cookies | `backend/api/auth/jwt.py:114` | `secure=True` whenever `ENVIRONMENT=production`; `samesite=lax`. JS cannot read the token. |
| CSP | `backend/api/main.py:57-62` | `script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self';`. No `unsafe-eval`. |
| Trusted-host | `backend/api/main.py` (`TrustedHostMiddleware`) | Enforces `ALLOWED_HOSTS`. Default: `localhost,127.0.0.1,[::1]`. Override with `YACHT_ALLOWED_HOSTS=…`. |
| CORS | `CORSMiddleware`, `settings.CORS_ORIGINS` | Defaults to localhost variants; override with `YACHT_CORS_ORIGINS=…`. |
| HTML sanitisation | `frontend/src/main.js` | `$sanitize` uses DOMPurify with an explicit allowlist (`b,i,em,strong,a,p,br,ul,ol,li,code,pre`, only `http(s)`/`mailto:` URLs). |
| Brute-force protection | `backend/api/routers/users.py` | `slowapi` rate limit `5/minute` on `/login` and `/login_cookie`, plus IP-restriction + `LoginAttempt` table for fail2ban-style blocking. |
| Secret key | `backend/api/settings.py:8-39` | Reads `SECRET_KEY` env first, otherwise persists to `$SECRET_KEY_FILE` (default `/config/.secret_key`). **Refuses to start** if it can't be loaded or written — no ephemeral per-process fallback. |
| 2FA enforcement | `backend/api/routers/setup/setup.py:165-169` | `/finalize` rejects accounts without 2FA. |
| Setup-pending token | `setup.py:144` | 15-minute lifetime, blocked by `auth_check_setup_pending` once setup is complete (prevents stale-token replay). |

---

## Running it

### Docker Compose (recommended)

```yaml
version: "3"
services:
  yachtplus:
    image: ghcr.io/yachtplus/yachtplus:devel
    container_name: yachtplus
    restart: unless-stopped
    ports:
      - "8000:8080"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./config:/config
    environment:
      # Pin a SECRET_KEY in production; otherwise the value is generated
      # once and persisted to /config/.secret_key.
      # SECRET_KEY: change-me-to-a-long-random-string
      ENVIRONMENT: production
      YACHT_ALLOWED_HOSTS: yachtplus.example.com,localhost
      YACHT_CORS_ORIGINS: https://yachtplus.example.com
```

```bash
docker-compose up -d
# → open http://<host>:8000 and run through the setup wizard
```

`/var/run/docker.sock` and `/config` are **mandatory** mounts — without them apps can't be managed and credentials can't be persisted across restarts.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | — | JWT signing key. If unset, persisted file `SECRET_KEY_FILE` is used. |
| `SECRET_KEY_FILE` | `/config/.secret_key` | Where the generated key is stored if `SECRET_KEY` is unset. Must be writable. |
| `ENVIRONMENT` | `development` | When `production`, cookies are sent with `Secure` flag (HTTPS only). |
| `SECURE_COOKIES` | derived from `ENVIRONMENT` | Override cookie `Secure` flag explicitly. |
| `DATABASE_URL` | `sqlite:////config/yacht.db` | SQLAlchemy URL. `postgresql://` / `mysql+pymysql://` also supported. |
| `YACHT_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | Comma-separated list for `TrustedHostMiddleware`. |
| `YACHT_CORS_ORIGINS` | `http://localhost,…` | Comma-separated list for `CORSMiddleware`. |
| `DOCKER_HOST` | `unix:///var/run/docker.sock` | Used by both `aiodocker` and the `docker` SDK. |
| `DOCKER_GID` | autodetected | Set to host's docker socket GID if you hit permission errors (`stat -c '%g' /var/run/docker.sock`). |
| `DISABLE_AUTH` | `False` | **Dev only.** Skips all auth checks. Never set this in production. |

---

## Local development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # Linux/macOS
# .\.venv\Scripts\Activate.ps1                       # Windows / PowerShell
pip install -r requirements.txt
# On Windows, uvloop is not supported — strip that line first:
#   pip install -r <(grep -v '^uvloop' requirements.txt)

# Backend listens on :8000
uvicorn api.main:app --reload --port 8000
```

The default `DATABASE_URL` points to `/config/yacht.db`, which doesn't exist outside the container. For local dev set:

```bash
export DATABASE_URL="sqlite:///./local.db"
```

### Frontend

```bash
cd frontend
npm install
npm run dev    # Vite dev server on :8080, proxies /api → :8000
```

Or build the production bundle into `frontend/dist/`:

```bash
npm run build
```

### Tests

Backend (pytest):

```bash
cd backend
DATABASE_URL="sqlite:///./test.db" python -m pytest tests/
```

Frontend (vitest):

```bash
cd frontend
npx vitest run
```

Current state: **213 backend tests + 9 frontend tests, all green.**

---

## Project layout

```
backend/
  api/
    main.py                  # FastAPI entrypoint, middleware stack, router includes
    settings.py              # Pydantic settings + SECRET_KEY bootstrap
    auth/
      jwt.py                 # JWT encode/decode, AuthWrapper, cookie helpers
      auth.py                # auth_check / auth_check_setup_pending / check_permission
    routers/
      apps.py                # /api/apps   container lifecycle + SSE stats stream
      compose.py             # /api/compose project CRUD
      containers.py          # /api/containers WS exec terminal
      dashboard.py           # /api/dashboard host metrics
      templates.py           # /api/templates  app-template registries
      users.py               # /api/auth login / refresh / API keys / user CRUD
      auth_2fa.py            # /api/auth/2fa generate / enable / disable
      setup/setup.py         # /api/setup status / register / finalize
      ... (resources, audit, registries, smtp, search, watchtower, settings)
    actions/                 # Business logic, mostly async wrappers around aiodocker/subprocess
    utils/                   # Pure helpers: compose parsing, crypto, audit, sanitiser
    db/                      # SQLAlchemy models, CRUD, alembic migrations
    services/                # Background jobs (watchtower poll, audit retention)
  alembic/                   # Database migrations
  tests/                     # pytest suite (213 tests)
  requirements.txt           # Production deps
frontend/
  src/
    main.js                  # App bootstrap, DOMPurify allowlist, axios interceptor
    App.vue
    router/                  # vue-router 4
    store/modules/           # Vuex 4 modules (auth, apps, projects, snackbar, …)
    plugins/
      vueutils.js            # Global properties: $formatDate, $timeAgo, $truncate (dayjs)
      vuetify.js
    views/
      auth/Login.vue         # Cookie-based login + 2FA flow
      Home.vue
      Setup.vue              # Setup wizard
      …
    components/
      auth/, applications/, compose/, charts/, ContainerTerminal.vue, …
    utils/
      imageLogos.js          # + .test.js (vitest)
  vite.config.js
  package.json
Dockerfile                   # Multi-stage: build SPA → install backend → run via gunicorn + nginx
docker-compose.yml           # Example production layout
nginx.conf                   # Routes /api → gunicorn, / → SPA
```

---

## Operational notes

- **First startup hangs?** Likely waiting on `/var/run/docker.sock`. Verify the mount and your `DOCKER_GID`.
- **428 Precondition Required on every API call?** Setup is not finalized — open `/setup` in the browser.
- **403 "Setup is pending, restricted access"?** A `setup_pending=True` token is being used after setup completed. Logout (clears cookie) and login again.
- **`SECRET_KEY could not be loaded or created`?** Either set `SECRET_KEY` explicitly or make sure `SECRET_KEY_FILE` (default `/config/.secret_key`) is on a writable volume.
- **Stale browser session after deploy?** Re-login. JWT signing key didn't change unless you wiped `/config`.

See [DEBUGGING_CHEATSHEET.md](DEBUGGING_CHEATSHEET.md) for a longer triage checklist.

---

## License

MIT
