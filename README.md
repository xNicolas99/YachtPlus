# YachtPlus

YachtPlus is a self-hosted container management UI for Docker and Docker Compose. It focuses on 1‑click template deployments while keeping the security defaults sane for self-hosting scenarios.

---

## Using the interface

The sidebar groups containers, images, volumes and networks under Workspace;
Compose stacks and templates are under Orchestration. Use the arrow beside
the brand to collapse or expand the sidebar. On small screens, open navigation
with the menu button in the top bar.

Resource tables search and paginate the complete resource list. Row menus
open actions without navigating to details. Failed creation and deletion
requests preserve the form or confirmation so you can correct the problem
and retry. Prune actions ask for confirmation and affect the whole Docker host.

Deploy containers in four steps: General, Networking, Volumes and Environment.
Advanced settings hold command, device, label, sysctl, capability and runtime
options. Required fields are checked before deployment.

Both search fields share the same result handling. Use Up/Down to select,
Enter to open and Escape to close results. The global search is also available
on mobile. Failed or timed-out searches show a Retry action; outdated results
cannot replace a newer query.

The terminal downloads only when opened. If it cannot load, retry or close it.
A failed page download keeps the current page and offers Retry page. Reload
application is a separate action because it discards unsaved inputs.

Local frontend development requires Node.js 20.19 or newer in the 20.x line,
or Node.js 22.12 or newer. Docker and CI use Node.js 22. The UI version defaults to `frontend/package.json`;
release builds can override it with `VITE_VERSION`.

Charts use Docker's cache-adjusted memory usage. Container logs show bounded
history (up to 10,000 lines), including for stopped containers, and stop their
stream on completion or failure. The terminal uses the maintained `@xterm`
packages and loads when opened; fonts are served locally.

## Build and publication checks

`npm run build` also checks the emitted manifest, assets, version metadata and bundle budgets:
300 kB entry JavaScript, 550 kB initial JavaScript including static dependencies,
and 700 kB initial CSS (uncompressed bytes, decimal kB). Terminal, editor and
statistics must remain outside the startup dependency graph; the terminal
must also remain outside the applications list's static graph.

GHCR publication runs only after successful validation in `ci.yml`, for pushes
to `master` or matching `vMAJOR.MINOR.PATCH` tags in the original repository.
Pull requests, forks, manual runs and failed/cancelled validation do not publish.
The publication gate checks the checked-out commit and canonical package/lock
version. A candidate image must pass its smoke test, startup and health check
before registry login and publication. A separate required `security-stack` job
starts the real nginx/backend/fail2ban stack and verifies bans and protection
outages; publication rejects a missing, failed or skipped security job. Ruff
remains an informational check.
Version-tag runs do not move `latest`. Tags are pushed sequentially, so an
interruption can leave a partial set of tags; the tested image is not rebuilt.
Workflow actions are pinned to commit SHAs. Python runtime and development
dependencies use separate committed locks with distribution hashes; test
tooling and backend tests are excluded from the release image. The downloaded
Compose plugin is checked against its release checksum.

---

## Tech stack

| Layer | Stack |
|---|---|
| Frontend | Vue 3.4, Vite 7, Vitest 4, Vuetify 3, Vuex 4, vee-validate v4 |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, aiodocker, APScheduler |
| Auth | JWT in HttpOnly cookies, mandatory 2FA (TOTP), bcrypt password hashing, slowapi rate limiting |
| Storage | SQLite by default (`/config/yacht.db`), Postgres/MySQL supported via `DATABASE_URL` |
| Packaging | Single Docker image, frontend built with Vite, served via nginx, FastAPI behind gunicorn |

---

## Architecture in one minute

```
Browser ──► nginx (port 8080) ──► /api/*  ──► gunicorn (FastAPI, /api)
                              └──► /        ──► static SPA from frontend/dist

FastAPI ──► aiodocker  ──► isolated Docker socket proxy ──► Docker daemon
        ──► SQLAlchemy ──► /config/yacht.db (default)
        ──► APScheduler (background jobs: Compose updates, audit cleanup)
```

The container ships **one** image with both frontend and backend. nginx routes API traffic to gunicorn and static traffic to the built SPA. The frontend talks to the API over same-origin so the HttpOnly auth cookie is sent automatically. The image health check probes `/api/setup/status`, including before first-run setup is complete.

---

## Auth & setup flow

The first launch is intentionally locked down:

1. **`GET /api/setup/status`** — frontend checks if first-time setup is required.
2. **`POST /api/setup/register`** — creates the first admin user with `is_active=False`, issues a short-lived JWT (15 min) with the `setup_pending=True` claim inside an HttpOnly cookie. Body returns only `{login, username}`, never the token.
   If the wizard was interrupted, the same username and password resume it;
   a different account cannot register while setup is pending.
3. **`POST /api/auth/2fa/generate`** + **`POST /api/auth/2fa/enable`** — admin scans the TOTP QR and confirms a 6-digit code. These endpoints accept `setup_pending=True` tokens but only while setup is incomplete.
4. **`POST /api/setup/finalize`** — verifies 2FA is enabled, flips `is_active=True`, marks setup complete, and issues a fresh token without `setup_pending`.

Two defense layers ensure a `setup_pending=True` token can't touch user data:

- **`check_setup_status` middleware** (`backend/api/main.py`): returns `428 Precondition Required` on any `/api/*` route except `/api/auth` and `/api/setup` until setup is finalized.
- **`auth_check` dependency** (`backend/api/auth/auth.py`): rejects `setup_pending=True` tokens with `403 "Setup is pending, restricted access"`. Used by every data router.

Subsequent logins go through **`POST /api/auth/login_cookie`**, which validates credentials, requires the TOTP code, and sets the HttpOnly cookie. The frontend never sees the raw JWT — it stays in the cookie jar and is sent automatically with every API call.

Every authenticated request validates that the account is active and the
token's credential version still matches. Password, username, permissions and
2FA changes invalidate existing sessions and API keys. Changing your username
or password requires your current password and returns you to login. User
management preserves at least one active administrator, including during
concurrent changes; administrators cannot disable or demote themselves.

TOTP codes are consumed once for their matched time step. After using a code
to enable 2FA or log in, wait for a new code before another confirmation.
Generating a secret is POST-only and cannot replace an enabled 2FA secret.

The API sets a separate readable `csrf_access_token` cookie. The frontend
sends it as `X-CSRF-TOKEN` for cookie-authenticated mutations; it contains no
JWT. Browser mutations and terminal connections require an exact matching
Origin, including scheme and port. Refresh requests share one in-flight
operation and revoke the previous token before issuing a replacement.

WebSocket exec sessions (container terminal) reuse the same cookie: `backend/api/routers/containers.py` reads `access_token_cookie` straight off the WS handshake; no token is ever passed in the URL.
The terminal closes when its token expires, is revoked, or loses the required
account permissions. Terminal input/output is never recorded in the audit log.

---

## Security defaults

| Defense | Where | Notes |
|---|---|---|
| HttpOnly cookies | `backend/api/auth/jwt.py` | `Secure` is inferred from HTTPS unless `SECURE_COOKIES` overrides it; `samesite=lax`. JS cannot read the token. |
| Cookie CSRF / WS Origin | `backend/api/utils/csrf.py` | Double-submit proof for cookie mutations; exact browser Origin and terminal Host checks. |
| CSP | `backend/api/main.py` | `script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self';`. No `unsafe-eval`; styles/fonts are local. |
| Trusted-host | `backend/api/main.py` (custom host middleware) | Enforces `ALLOWED_HOSTS`. Default: `localhost,127.0.0.1,[::1]`. Override with `YACHT_ALLOWED_HOSTS=…`. |
| CORS | `CORSMiddleware`, `settings.CORS_ORIGINS` | Defaults to localhost variants; override with `YACHT_CORS_ORIGINS=…`. |
| HTML sanitisation | `frontend/src/main.js` | `$sanitize` uses DOMPurify with an explicit allowlist (`b,i,em,strong,a,p,br,ul,ol,li,code,pre`, only `http(s)`/`mailto:` URLs). |
| Brute-force protection | `fail2ban/`, `api/utils/access_policy.py`, `api/utils/security.py` | Real fail2ban: 5 failures in 15 minutes, one-hour ban across UI/API/WS. Mandatory protection fails closed when stale or unavailable. Login rate limits and account lockout remain independent. |
| LAN access | `api/utils/access_policy.py`, `nginx.conf` | Default applies to all traffic, including setup and static UI; explicit local administrator confirmation is required for public access. |
| Workload profiles | `api/utils/container_security.py` | Restricted defaults: nonzero numeric user, read-only rootfs, dropped capabilities, no new privileges and bounded processes. Explicit administrator compatibility mode is available for incompatible images. |
| State-changing routes | `routers/apps.py`, `routers/compose.py`, `routers/templates.py` | Mutations use POST/DELETE; legacy mutating GET aliases are removed, including template refresh and 2FA generation. |
| 2FA enforcement | `backend/api/routers/setup/setup.py` | `/finalize` rejects accounts without 2FA; successful codes cannot be replayed. |
| Setup-pending token | `backend/api/routers/setup/setup.py` | 15-minute lifetime, blocked by `auth_check_setup_pending` once setup is complete. |
| Secrets at rest | `backend/api/utils/crypto.py`, `secret_files.py` | TOTP/SMTP ciphertext uses the persisted signing key and salt; atomic publication prevents partial key files. Invalid existing key/salt files fail rather than being replaced. |
| Remote template fetches | `backend/api/db/crud/templates.py` | DNS-pinned public addresses, guarded redirects, 15-second body deadline and 5 MiB limit. Yacht/Portainer v2 imports are supported. |
| Audit / retention | `backend/api/utils/audit_middleware.py` | Successful mutations and login outcomes are recorded without bodies/secrets. Hourly cleanup defaults to 90 days for activity, 30 days for login attempts. The database audit log is not immutable storage. |

### Permission model

YachtPlus uses four action permissions on the `User` model:
`perm_start`, `perm_stop`, `perm_restart`, and `perm_delete`.
Superusers bypass all permission checks.

There is **no dedicated `perm_read` permission**. Read-only views such as
the Docker Compose project list are therefore gated behind `perm_start`,
the lowest operator permission. This is intentional: even "read" access
to a container orchestrator exposes configuration, environment variables,
and runtime state that can be abused to escalate privileges.

API keys are restricted to GET/HEAD data access with the issuing user's
existing permissions. They cannot use `/api/auth`, refresh sessions, change
settings, mutate containers/stacks, or open a terminal. The bearer token is
returned once at creation; the database stores its JTI, expiry and a SHA-256
digest of the random JTI. Revocation and account changes take effect immediately.

SMTP settings require an administrator. The UI receives only whether a
password is configured; it never receives the saved password. Leaving the
password unset retains it. SMTP uses verified TLS and a network timeout.

---

## Running it

### Docker Compose (recommended)

Use the checked-in `docker-compose.yml`; both deployment examples include the
same mandatory protection services. From this checkout:

```bash
docker compose up -d --build
docker compose ps
# Open http://localhost:8000 or http://<server-LAN-IP>:8000
```

Compose waits for a healthy fail2ban jail before starting YachtPlus. YachtPlus
runs as UID/GID 1000:1000, fail2ban as 1001:1000; neither needs root, a Docker
socket mount or firewall capabilities. Writable data lives in named volumes;
the app root filesystem is read-only and all Linux capabilities are dropped.
The Docker socket proxy is isolated on `docker_api` without a published port.
It still grants powerful Docker management access and is not a payload sandbox.
The Docker daemon and socket proxy are separate infrastructure; this Compose
file does not turn a rootful Docker daemon into a rootless one.

LAN IP literal access works by default. Add an explicit hostname with
`YACHT_ALLOWED_HOSTS` in `.env` when using DNS. Public source addresses are
blocked for the UI, API, setup and terminal, including authenticated traffic.
Local means loopback, IPv4 RFC1918 and IPv6 ULA; link-local, multicast,
unspecified and reserved source addresses are not treated as LAN clients.

An active administrator connected locally can opt in at **Server Settings →
Security → Network Access & Protection**, with explicit confirmation. Public
access requires mandatory, healthy fail2ban; there is no protection-disable
switch. The policy persists in `/config/access-policy.json`. The historical
`YACHT_BLOCK_PUBLIC_IP_LOGIN=false` flag no longer opens public access.

If an external HTTP proxy is used, configure its exact IP/CIDR through
`YACHT_HTTP_TRUSTED_PROXIES` and recreate the app. nginx validates the trusted
chain and overwrites client headers. Keep backend `YACHT_TRUSTED_PROXIES` at
`127.0.0.1,::1`; never trust every LAN client as an HTTP proxy. See
[secure deployment and migration](docs/SECURITY_DEPLOYMENT.md).

The named volumes preserve the database, signing keys, Compose files, security
logs and bans. Existing bind mounts must already be owned by UID/GID 1000:1000;
the new startup does not perform root ownership repairs. Back up existing data
before migration. See the migration guide for ownership and policy changes.

The credential migration adds account token versions and TOTP replay state,
and encrypts existing SMTP passwords. Back up the database, signing key and
Fernet salt together. Existing tokens without the new version claim require
login again; create replacement API keys after upgrading.

Compose projects support `compose.yaml`, `compose.yml`, `docker-compose.yaml`
and `docker-compose.yml` in direct project directories. YAML must be valid
before an atomic save; the existing filename is preserved. Deletion runs
`docker compose down` before removing files and retains them if shutdown fails.
Daily automatic Compose updates are disabled by default; set
`COMPOSE_AUTO_UPDATE=true` to opt in. Manual updates report their completed
result instead of returning success while the job is still pending.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | — | JWT signing key with at least 32 bytes. If unset, persisted file `SECRET_KEY_FILE` is used. |
| `SECRET_KEY_FILE` | `/config/.secret_key` | Atomic persisted signing key; default falls back to `.secret_key` locally when `/config` is absent. |
| `FERNET_SALT_FILE` | `/config/.fernet_salt` | Atomic 16-byte at-rest crypto salt; falls back to `.fernet_salt` if the parent directory is absent. Preserve it with the key and DB. |
| `ENVIRONMENT` | `development` | Deployment-mode diagnostics; does not alone force Secure cookies. |
| `SECURE_COOKIES` | auto (HTTPS request) | Override cookie `Secure` flag explicitly. |
| `SAME_SITE_COOKIES` | `lax` | Cookie SameSite setting; cookie mutations still require CSRF proof. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Normal token/cookie lifetime in minutes; setup uses 15 minutes. |
| `DATABASE_URL` | `sqlite:////config/yacht.db` | SQLAlchemy URL. `postgresql://` / `mysql+pymysql://` also supported. |
| `YACHT_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | Comma-separated list for `TrustedHostMiddleware`. |
| `YACHT_ALLOW_PRIVATE_NETWORK_HOSTS` | `false` in source; enabled in Compose | Permit private/link-local IP literal Host headers; use explicit hostnames for DNS access. |
| `YACHT_CORS_ORIGINS` | `http://localhost,…` | Comma-separated list for `CORSMiddleware`. |
| `DOCKER_HOST` | `unix:///var/run/docker.sock` | Used by both `aiodocker` and the `docker` SDK. |
| `DISABLE_AUTH` | `False` | **Dev only.** Skips all auth checks. Never set this in production. |
| `YACHT_BLOCK_PUBLIC_IP_LOGIN` | `true` | Historical flag retained for configuration compatibility; does not bypass the persisted global access policy. |
| `YACHT_ACCESS_POLICY_FILE` | `/config/access-policy.json` | Explicit persisted public-access policy; missing file means local-only. |
| `YACHT_FAIL2BAN_REQUIRED` | `true` in the image and Compose; `false` for direct source development | Fail closed if protection is unavailable. Public access requires this to be true. |
| `YACHT_FAIL2BAN_STATE_DIR` | `/run/yachtplus-security` | Sidecar writes readiness and bans; app mounts this read-only. |
| `YACHT_SECURITY_LOG` | `/config/security/auth.log` | Persistent deterministic login-failure log read by fail2ban. |
| `YACHT_HTTP_TRUSTED_PROXIES` | empty | Validated HTTP proxy IPs/CIDRs used by nginx for client-IP and HTTPS attribution. |
| `YACHT_TRUSTED_PROXIES` | `127.0.0.1,::1` | Backend peers permitted to supply normalized client headers. |
| `YACHT_DOCKER_PROXY_NETWORK` | `${COMPOSE_PROJECT_NAME:-yachtplus}_docker_api` in Compose | Network used by rootless update workers; updates never mount the host socket. |
| `COMPOSE_DIR` | `/compose/` | Compose project directory; trailing slash is optional. |
| `COMPOSE_AUTO_UPDATE` | `false` | Enable daily automatic Compose pull/recreate jobs. |
| `AUDIT_RETENTION_DAYS` | `90` | Activity log retention, cleaned hourly; minimum 1 day. |
| `LOGIN_RETENTION_DAYS` | `30` | Login-attempt retention, cleaned hourly; minimum 1 day. |
| `RATE_LIMIT_STORAGE_URI` | `memory://` | slowapi storage backend; the image runs one API worker so limits are shared by all its requests. Custom multiple-worker deployments need shared storage and its client dependency. |
| `YACHT_DEFAULT_TEMPLATE_URLS` | SelfhostedPro and Portainer Community URLs | Comma-separated `Title\|URL` seeds on first finalize; an empty value disables remote seeds. |
| `YACHT_BUILTIN_CATALOG_DIR` | `/api/configs` | Bundled JSON catalogs for initial setup, including offline use. |
| `SETUP_FLAG_FILE` | `/config/.setup_completed` | Legacy setup marker, restricted to safe paths; setup status is also persisted in the database. |
| `ENV_FILE` | unsupported | Legacy override with no current effect; source settings read `.env` through Pydantic. |

---

## Local development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # Linux/macOS
# .\.venv\Scripts\Activate.ps1                       # Windows / PowerShell
pip install --require-hashes -r requirements-dev.lock
# On Windows, uvloop is skipped automatically by its dependency marker.

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
npm ci
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

Run publication-policy checks from the repository root with the backend
environment: `python -m unittest discover -s scripts -p 'test_*.py' -v`.
Local verification on 2026-10-02 passed **852 backend, 197 frontend and 42
publication-policy tests**. The latest [changelog](CHANGELOG.md) and
[remediation report](docs/AUDIT_REMEDIATION_2026-10-02.md) record the completed
checks and remaining work. Older audit documents contain historical counts.
The candidate still requires Docker/runtime verification before release.

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
  tests/                     # pytest suite, excluded from release image
  requirements.txt           # Runtime dependency input
  requirements.lock          # Exact hashed runtime resolution
  requirements-dev.txt       # Runtime input plus test tooling
  requirements-dev.lock      # Hashed development resolution
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
      auth/Setup.vue         # Setup wizard
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

- **Docker actions fail?** Check the `dockerproxy` service, its API-section flags and the `DOCKER_HOST` setting.
- **428 Precondition Required on every API call?** Setup is not finalized — open `/setup` in the browser.
- **403 "Setup is pending, restricted access"?** A `setup_pending=True` token is being used after setup completed. Logout (clears cookie) and login again.
- **`SECRET_KEY could not be loaded or created`?** Either set `SECRET_KEY` explicitly or make sure `SECRET_KEY_FILE` (default `/config/.secret_key`) is on a writable volume.
- **Stale browser session after deploy?** Re-login. The credential migration rejects older tokens without an account version even when the persisted signing key is unchanged. Preserve `/config` and regenerate API keys when required.
- **403 on a cookie-authenticated mutation?** Send `X-CSRF-TOKEN` matching `csrf_access_token` and use the same browser origin. Reverse proxies must preserve the external host and attribute HTTPS through the configured trusted proxy path.
- **2FA code rejected after a successful operation?** Codes are single use per matched step; wait for the next code before another confirmation.

See [DEBUGGING_CHEATSHEET.md](DEBUGGING_CHEATSHEET.md) for a longer triage checklist.

---

## License

MIT
