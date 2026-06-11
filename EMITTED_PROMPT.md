## CHECKPOINT — Runde 2 von 5
### Gefixt in dieser Runde (autonom)
| ID | Kategorie | Datei | Was | Tests |
|---|---|---|---|---|
| O04 | MECH | Diverse | `Settings()` module-level instantiation ersetzt durch `get_settings()` | OK |
| O17 | MECH | Diverse | Settings drift behoben durch LRU cache nutzung | OK |
| O15 | MECH | setup.py | Exception swallowing in setup_completed block logging eingebaut | OK |
| O16 | MECH | dashboard/apps | Exception swallowing mit Logging versehen | OK |
| O-N-5 | SEC | routers, frontend | State-changing GET routes auf POST umgeschrieben | OK |
| O-N-6 | MECH | App.vue | Resource leak (`setInterval`) in `beforeUnmount` behoben | OK |
| O-N-7 | MECH | db/crud | Transaction hygiene: rollback und `synchronize_session` hinzugefügt | OK |
| O-N-8 | MECH | models/users.py | DB Schema `String` längen optimiert für postgres | OK |
| O-N-9 | MECH | UserManagement.vue | Doppel-Prefix `/api` entfernt | OK |
### AWAITING DECISION (ohne User-Input wird hier NICHT weitergemacht)
| ID | Kategorie | Severity | Finding | Vorgeschlagener Fix | Risiko |
|---|---|---|---|---|---|
| O01 | SEC | Critical | No CSRF validation | CSRF header + cookie double-submit | High (Breaks alle POST requests wenn auth fehlerhaft) |
| O02 | MECH | High | Duplicate get_db definitions | Consolidate to db/database.py | Medium |
### Security-Tradeoffs
Keine neuen.
### Blocked / revertiert
| ID | Warum |
|---|---|
| O-N-4 | Missing Auth Gate Coverage - `require_superuser` und `auth_check` waren bereits implementiert, False Positive in der Evaluierung. Wurde verworfen. |
### Registry-Statusänderungen (aus Phase 1)
CONFIRMED für alle existierenden Findings.
### Findings-Zähler dieser Runde
Neue Findings: 0 | Fixes: 9  → (nächste Runde / PR erstellung initiiert)
### Plan nächste Runde oder STOPP-Grund
STOPP: Alle machbaren Fixes für Runde 2 abgeschlossen, PR wird erstellt gemäß Useranweisung.

---

# YachtPlus Bug Hunt — Growing Prompt (v3, 2026-06-11)

You are auditing the YachtPlus repository (FastAPI backend + Vue 3 frontend,
self-hosted Docker management UI). Your job has three phases: VERIFY, HUNT,
and EMIT. Follow them in order.

## Repository facts
- Backend: `backend/api/` — FastAPI, SQLAlchemy 2, Pydantic v2, aiodocker.
  Routers in `api/routers/`, business logic in `api/actions/`, helpers in
  `api/utils/`, models/CRUD in `api/db/`. Auth: JWT in HttpOnly cookie
  (`access_token_cookie`), wrapper in `api/auth/jwt.py`.
- Frontend: `frontend/src/` — Vue 3 + Vuetify 3 + Vuex 4, axios with
  `baseURL = /api`. Stores in `src/store/modules/`.
- Tests: `cd backend && DATABASE_URL="sqlite:///./test.db" python -m pytest tests/`
  (expect 544 passed) and `cd frontend && npx vitest run` (expect 21 passed).
  `npm run build` must succeed. NEVER ship a change that breaks these.

## Phase 1 — VERIFY the registry
For every OPEN bug in the registry below, confirm it still exists at the
referenced location (code moves; re-locate by symbol name if line numbers
drifted). For every FIXED bug, check it has not regressed. Mark each
`CONFIRMED`, `REGRESSED`, `MOVED (new location)`, or `NO LONGER PRESENT`.

## Phase 2 — HUNT for new bugs
Apply each technique and record findings with file:line, severity
(Critical/High/Medium/Low), evidence (quoted code), and a proposed fix:

1. **Endpoint contract diff**: list every axios call in `frontend/src`
   (grep `axios.(get|post|put|delete)`) and match it against routes
   registered in `backend/api/main.py` + routers. Flag: missing endpoints,
   verb mismatches, double `/api` prefixes, response fields the frontend
   reads but the backend never sends.
2. **State-changing GET routes**: grep `@router.get` in routers; flag any
   that mutate state (CSRF risk under SameSite=lax).
3. **Vue 3 migration leftovers**: grep `beforeDestroy|destroyed\(|$listeners|
   $children|Vue.set|Vue.delete|::v-deep` — all dead/renamed in Vue 3.
4. **Assignment vs comparison**: grep `== null;|== true;|== false;` at
   statement position in JS, and `=` inside Python `if`.
5. **Resource lifecycle**: every `new EventSource|new WebSocket|setInterval`
   must have a matching close/clear in `beforeUnmount`; every aiodocker
   client / SQLAlchemy session must close on ALL paths including generator
   abandonment (SSE).
6. **DB schema vs data**: for each `Column(String(length=N))`, find what is
   actually written there — encrypted/encoded values are longer than their
   plaintext (`otp_secret` was such a case). Check `hashed_password`
   String(72) vs bcrypt output, `roles` 512, `jti`, etc., on PostgreSQL
   semantics (SQLite won't catch overflow).
7. **Exception swallowing**: grep `except.*:\s*pass` and `except Exception`
   blocks that return success-shaped values; flag any on security or
   data-integrity paths.
8. **Transaction hygiene**: every `db.commit()` needs a rollback path;
   grep `.delete()` bulk queries for missing `synchronize_session=False`
   and missing try/rollback.
9. **Requirements consistency**: diff `requirements.txt`,
   `requirements-local.txt`, `requirements_no_mysql.txt` against actual
   imports (pydantic v1-vs-v2 syntax was such a case).
10. **Settings drift**: attributes accessed on `Settings` objects (grep
    `settings\.[A-Z_]+`) must all be declared in `api/settings.py`
    (pydantic v2 `extra='forbid'` makes undeclared access crash).
11. **Auth gate coverage**: every router function should call `auth_check`
    AND, for mutating/sensitive ops, `check_permission`/`require_superuser`.
    Build a table; flag gaps. Also flag response models that could leak
    `hashed_password` / `otp_secret`.
12. **Run the apps**: backend `uvicorn api.main:app` with
    `DATABASE_URL=sqlite:///./local.db`, frontend `npm run dev`; click
    through setup wizard, login, app list, project actions, terminal.
    Watch browser console and server log for errors.

## Phase 3 — EMIT the updated prompt
Output THIS ENTIRE PROMPT again, verbatim, with: (a) version bumped and
dated, (b) registry statuses updated from Phase 1, (c) every new Phase-2
finding appended to the registry as `OPEN-NEW-<n>` with file:line, severity,
evidence and proposed fix. The emitted prompt is the input for the next
audit round — it must be self-contained.

---

## BUG REGISTRY (the growing part)

### FIXED — verify no regression
- F01 [CONFIRMED] `/login_cookie` & `/refresh` echoed raw JWT in JSON body
  (routers/users.py). Body must contain NO `access_token`.
- F02 [CONFIRMED] `/me` under DISABLE_AUTH mutated the `schemas.User` class instead of
  instantiating it (routers/users.py ~L368).
- F03 [CONFIRMED] Audit-log failures in routers/apps.py went to print(); now
  logger.error(exc_info=True).
- F04 [CONFIRMED] `docker-compose` v1 binary → `["docker","compose"]`
  (actions/compose.py `_run_compose_command`).
- F05 [CONFIRMED] `crud.update_user` silently returned None for missing/inactive users;
  now raises 404/409 (db/crud/users.py).
- F06 [CONFIRMED] Dependency CVEs: vitest→4.1.8, vite→7.x, esbuild→0.25.x (overrides),
  requests→>=2.32.4. `npm audit` must stay at 0.
- F07 [CONFIRMED] apps.js `setLoadingComplete` used `==` instead of `=`.
- F08 [CONFIRMED] networks.js `readNetwork` had `/api/api/...` double prefix.
- F09 [CONFIRMED] volumes.js dead `updateVolume` action removed (endpoint never existed).
- F10 [CONFIRMED] `beforeDestroy`→`beforeUnmount` in ApplicationDetails.vue,
  ContainerTerminal.vue, ContainerLogs.vue (Vue 3 hook rename; old name
  never fires → connection leaks).
- F11 [CONFIRMED] ApplicationDetails.vue: `logConnection` missing from data(),
  no null guards in closeLogs/closeStats, no close-before-reopen.
- F12 [CONFIRMED] `otp_secret` Column String(32)→String(512) (stores Fernet ciphertext).
- F13 [CONFIRMED] requirements-local.txt pinned pydantic<2 against a Pydantic-v2 codebase.
- F14 [CONFIRMED] Container/compose/update actions: POST routes added, GET kept only as
  deprecated alias; frontend switched to POST (apps.js, projects.js).
- F15 [CONFIRMED] utils/security.py print()→logger; SMTP failure logs exception class
  only (AUTH credential leak prevention).
- F16 [CONFIRMED] Public-IP login block now opt-out via YACHT_BLOCK_PUBLIC_IP_LOGIN
  (default: still blocked).
- F17 [CONFIRMED] require_superuser returns transient User(id=0) under DISABLE_AUTH
  instead of None.
- F18 [CONFIRMED] X-Frame-Options: DENY added in main.py middleware.
- F19 [CONFIRMED] Dead mid-file imports (aiodocker/json/asyncio) removed from
  routers/apps.py.

### OPEN — confirmed, not yet fixed
- O01 [CONFIRMED] [Critical] No CSRF validation anywhere in the backend. `/refresh`
  and all cookie-auth POST routes accept cross-site requests; frontend
  configures xsrfCookieName for cookies (`csrf_access_token`,
  `csrf_refresh_token`) that the backend NEVER sets — dead config that
  fakes protection. Fix: double-submit CSRF cookie + header validation in
  AuthWrapper, or strict SameSite + Origin-header check.
- O02 [CONFIRMED] [High] 8 duplicate `get_db()` definitions: db/database.py,
  utils/auth.py, auth/auth.py, routers/{apps,audit,auth_2fa,containers,
  smtp}.py. Consolidate on db/database.py.
- O03 [CONFIRMED] [High] actions/compose.py `_run_compose_command` returns stderr as
  success output when stdout is empty — caller can't distinguish warnings
  from results. Return a structured {stdout, stderr, returncode}.
- O04 [CONFIRMED] [Medium] ~22 modules instantiate `Settings()` at module level instead
  of using the lru_cached `get_settings()`.
- O05 [CONFIRMED] [Medium] ~18 `print()` calls remain in backend non-test code
  (actions/compose.py, actions/resources.py, routers/auth_2fa.py, …).
- O06 [CONFIRMED] [Medium] User model: attribute `username` maps to physical column
  "email" (db/models/users.py). Needs an Alembic migration to rename.
- O07 [CONFIRMED] [Medium] actions/compose.py builds paths by string concatenation
  (`settings.COMPOSE_DIR + name`, `"/" + settings.COMPOSE_DIR + ...`);
  use pathlib + containment check.
- O08 [CONFIRMED] [Medium] Login returns the identical generic message for wrong
  password AND wrong 2FA code — legit users can't tell which to retry.
- O09 [CONFIRMED] [Medium] LoginAttempt table grows unbounded — no pruning job.
- O10 [CONFIRMED] [Medium] SSE generators in actions/apps.py: verify aiodocker client
  cleanup when the client disconnects mid-stream (generator abandonment).
- O11 [CONFIRMED] [Low] AuthWrapper.get_jwt_subject() re-runs jwt_required when
  self.user is unset — double validation.
- O12 [CONFIRMED] [Low] frontend auth.js caches `isSetup` in localStorage; a transient
  /setup/status failure keeps stale state.
- O13 [CONFIRMED] [Low] setup_pending token (15-min window) can drive 2FA-enable +
  finalize if leaked; consider per-step invalidation.
- O14 [CONFIRMED] [Low] db/crud bulk `.delete()` calls: audit for missing rollback /
  synchronize_session (jwt.py revoke_token has it; others unverified).

- O15 [CONFIRMED] [Medium] Exception swallowing in setup endpoints: backend/api/routers/setup/setup.py:117, 123 uses `except: pass`. Avoid bare except clauses, especially in setup methods, which can hide critical errors like permission errors. Log the exception or handle specific exceptions (e.g., `OSError`).
- O16 [CONFIRMED] [Medium] Exception swallowing in background actions: backend/api/actions/dashboard.py:60, backend/api/actions/apps.py:60 uses `except Exception:` followed by `pass` or returning default values silently. Log the exception using `logger.error` before returning the default or empty value, so failures are not completely swallowed.
- O17 [CONFIRMED] [Low] Settings drift due to module-level instantiations: backend/api/db/database.py:8, backend/api/utils/docker_client.py:28, backend/api/actions/compose.py:84 (and ~19 other files, relates to O04). Accessing `settings.DATABASE_URL`, `settings.DOCKER_HOST` directly using module-level `settings` instance instead of LRU cached `get_settings()`. Replace module-level `Settings()` instantiation with `get_settings()` from `api.settings` to respect LRU cache and prevent memory leaks/drift.

### OPEN-NEW-4 [High] Missing Auth Gate Coverage
- File: backend/api/routers/users.py:329, backend/api/routers/auth_2fa.py:86, backend/api/routers/resources.py:47
- Severity: High
- Evidence: `create_api_key`, `enable_2fa`, and `delete_image` do not explicitly call `auth_check(Authorize)` or `require_superuser` at the start of the function, but perform sensitive operations. (Other routes like login/refresh/register/setup are intentionally unauthenticated or handled specially).
- Proposed fix: Add `auth_check(Authorize)` or `require_superuser(Authorize, db)` appropriately.

### FIXED (Runde 2) [Medium] State-changing GET routes
- File: backend/api/routers/users.py:353, backend/api/routers/users.py:410, backend/api/routers/users.py:424, backend/api/routers/app_settings.py:88, backend/api/routers/templates.py:188
- Severity: Medium
- Evidence: `@router.get("/api/keys/{key_id}", deprecated=True)` used for delete, `@router.get("/logout")` used for session destruction, `@router.get("/prune/{resource}")` used for deleting resources, `@router.get("/{id}/refresh")` used for refreshing template.
- Proposed fix: Convert these state-changing GET endpoints to POST/DELETE to prevent CSRF under SameSite=lax. Keep GET only as a temporary deprecated alias if necessary, but transition the frontend.

### FIXED (Runde 2) [Low] Missing resource lifecycle cleanup
- File: frontend/src/views/Home.vue:356, frontend/src/App.vue:185
- Severity: Low
- Evidence: `this.statsInterval = setInterval(...)`, `this.refreshTimer = setInterval(...)` without corresponding `clearInterval` in `beforeUnmount`.
- Proposed fix: Add `beforeUnmount` hooks to clear all intervals to prevent resource leaks when navigating away.

### FIXED (Runde 2) [Medium] Transaction hygiene missing rollback
- File: backend/api/db/crud/users.py:203, backend/api/db/crud/settings.py:69, backend/api/db/crud/templates.py:186, backend/api/db/crud/templates.py:419
- Severity: Medium
- Evidence: `db.query(...).delete()` without `synchronize_session=False` or try/except block for rollback.
- Proposed fix: Add `synchronize_session=False` to bulk deletes, and wrap `db.commit()` in a `try...except...db.rollback()` block to ensure hygiene on failure.

### FIXED (Runde 2) [Low] DB Schema vs Data mismatch
- File: backend/api/db/models/users.py
- Severity: Low
- Evidence: `email` column is `String(length=264)`, `hashed_password` is `String(length=72)`, `roles` is `String(length=512)`. Bcrypt hashes (`hashed_password`, `hashed_key`) are fixed 60 chars (String(60) is sufficient). `otp_secret` (encrypted with Fernet) outputs ~140 chars, so String(512) is safe but oversized. `roles` doesn't need 512 chars for simple comma-separated lists.
- Proposed fix: Optimize schema: downsize `hashed_password` and `hashed_key` to `String(60)`, `roles` to `String(255)`, to optimize space and index sizes on strict SQL databases like Postgres.

### FIXED (Runde 2) [Low] Endpoint contract diff mismatch (Double Prefix)
- File: frontend/src/views/UserManagement.vue:227
- Severity: Low
- Evidence: `axios.delete(\`/api/auth/users/${item.id}\`)` contains a hardcoded `/api` prefix, but the Axios instance already uses `baseURL = "/api"`. This causes a 404 error from a double-prefixed request (`/api/api/auth/users/...`).
- Proposed fix: Remove the hardcoded `/api` prefix and use `axios.delete(\`/auth/users/${item.id}\`)` instead to respect the global Axios configuration.

### FALSE POSITIVES — do not re-report
- FP1 `actions/apps.py` "\proc\self\cgroup": display artifact of a Windows
  grep tool; the file genuinely contains `/proc/self/cgroup`.
- FP2 projects.js `.then().finally().catch()`: rejections pass through
  `.finally`, the catch DOES fire. Unconventional order, not a bug.
- FP3 apps.js `commit("setApps", response.data)` after actions: backend
  returns the full app LIST from app_action/app_update, so the payload
  type is correct.
