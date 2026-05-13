# Repository Knowledge Base (Jules Context)

## 🏗️ Architecture & Stack
- **Core Stack:** Vue 3 (Vite), FastAPI (Python), SQLite/SQLAlchemy, Docker.
- **Architecture Pattern:** Decoupled SPA (Single Page Application) frontend communicating with a RESTful FastAPI backend. The application acts as a container management UI, directly interacting with the Docker daemon socket (`/var/run/docker.sock`).
- **Key Dependencies:**
  - **Frontend:** Vuetify 3 (UI framework), Pinia & Vuex (State Management), Axios (Data fetching), Vee-Validate 4 (Form validation), vue-chartjs & Chart.js (Charts).
  - **Backend:** FastAPI, SQLAlchemy (ORM), Pydantic (Validation & Settings), Uvicorn (ASGI server), aiodocker/docker (Docker API clients), PyJWT (Authentication).

## 🗺️ Project Map
- `/backend/api` -> Core backend application logic, divided into distinct routers, database access (CRUD), and utility modules.
- `/backend/api/routers` -> Contains the FastAPI routing logic separated by feature domain (e.g., `apps`, `auth`, `containers`, `setup`).
- `/backend/api/db` -> Database models, Pydantic schemas, and SQLAlchemy setup.
- `/frontend/src/views` -> Main top-level page components representing application routes.
- `/frontend/src/components` -> Reusable Vue 3 components used within views.
- `/frontend/src/store` & `/frontend/src/stores` -> `store` is used for legacy Vuex state management (e.g., auth), while `stores` is for newer Pinia stores.
- `/frontend/src/plugins` -> Global Vue plugins and configurations (Vuetify, VueUtils, webfontloader).

## 📜 Coding Conventions & Rules
- **State Management:** The frontend is transitioning. It uses both Vuex (legacy auth) and Pinia (new components). Avoid redundant network requests by using local state for things like running containers (`store.state.apps.apps`) when building search components.
- **Data Fetching:** Always use Axios via the pre-configured instance (`axios.defaults.baseURL` is set to include `/api`). Independent API requests during initial loading must be executed concurrently using `Promise.all()` to optimize performance.
- **Error Handling:**
  - Backend throws FastAPI `HTTPException`. Database updates that violate unique constraints must catch exceptions, execute `db.rollback()`, and raise a 400 `HTTPException`.
  - Frontend catches these via Axios interceptors, specifically one that handles token refreshes.
- **Styling:** Vuetify 3. For Vuetify dialog action buttons (`<v-card-actions>`), consistently apply the `text` attribute to 'Cancel' buttons and use semantic colors (e.g., `color="error"`) instead of hardcoded colors for destructive 'Continue' buttons.
- **Component Practices:**
  - **Buttons:** For Vuetify buttons triggering async operations, always implement `:loading` and `:disabled`. When grouped, track the specific active item (e.g., `loadingResource === 'item'`) to localize the spinner while using a global `:disabled` flag.
  - **Search:** Components must clear their result arrays immediately upon user input before debounce/API calls to prevent stale data.
  - **Logs:** Auto-scrolling utilizes a Vue 3 `watch` on log data arrays triggering `$nextTick` to update `scrollTop`, avoiding legacy `v-chat-scroll`.
  - **Editors:** Use `vue3-ace-editor` with `v-model:value` for content binding.
- **Security & Setup:**
  - **Strict CSP:** Implemented in `main.py` middleware `script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self';` without `unsafe-eval`.
  - **IP Restrictions & SSRF:** URL validation functions must catch `socket.gaierror` and explicitly raise 400 `HTTPException`. Must explicitly check `is_loopback`, `is_link_local`, `is_multicast`, and `'0.0.0.0'` alongside `.is_private`.
  - **IP Spoofing:** Securely parse client IP by prioritizing `request.client.host` or `X-Real-IP`. If using `X-Forwarded-For`, parse right-to-left.
  - **Setup Enforcement:** Setup bypass is restricted to 0 users. Auth endpoints issue HttpOnly access cookies via `Authorize.set_access_cookies`. Setup-specific routes must explicitly use `auth_check_setup_pending`.
  - **Timing Attacks:** Login routes verify passwords exactly once testing against either the user's real hash or a static `DUMMY_HASH`.
  - **Injection:** `subprocess.run` user-controlled arguments must be strictly validated using a regex (e.g., `^[a-zA-Z0-9_-]+$`).
- **Backend Performance:** Synchronous DB calls within async endpoints must be wrapped in `fastapi.concurrency.run_in_threadpool` to avoid event-loop starvation. External requests in endpoints like unified search should run concurrently with synchronous DB calls.
- **Proxy Configuration:** Nginx (`nginx.conf`) proxy `/api/` requests to `http://127.0.0.1:8000` *without* a trailing slash.
- **Journaling:** Agent learnings should be stored in `.jules/palette.md` (UX/Accessibility), `.jules/sentinel.md` (Security), `.jules/mechanic.md` (Testing/Logic), and `.jules/bolt.md` (Performance).
- **Date Handling:** `dayjs` is strictly for global Vue date formatting (`$formatDate` and `$timeAgo`), `date-fns` is strictly for `chartjs-adapter-date-fns`.
- **Accessibility:** Icon-only buttons (like Vuetify `<v-btn icon>`) must always include descriptive `aria-label` and `title` attributes.

## 🧪 Testing & Commands
- **Test Runner:**
  - **Frontend:** Vitest.
  - **Backend:** Pytest (requires `pytest-asyncio` for async tests using `@pytest.mark.asyncio`, heavy reliance on `unittest.mock`).
  - **E2E/Frontend UI:** Playwright Python scripts.
- **Key Commands:**
  - **Frontend Build/Dev:** `cd frontend && pnpm install && pnpm build` (Strictly `pnpm`, no `npm` or `yarn`), `cd frontend && pnpm dev`.
  - **Frontend Tests:** `cd frontend && pnpm vitest run`.
  - **Frontend UI Verifications:** Local preview server started with `cd frontend && pnpm run preview` on port 4173.
  - **Backend Dev:** `cd backend && python3 main.py`.
  - **Backend Tests:** `cd backend && DATABASE_URL=sqlite:///:memory: PYTHONPATH=. python3 -m pytest tests/`.
- **Testing Rules:**
  - Mock `subprocess.run` in Docker-related tests to prevent host execution.
  - Test SSRF mitigation by mocking `socket.getaddrinfo` to simulate multiple IP resolutions and `socket.gaierror`.
  - Pass mock objects directly for testing isolated dependency functions.
  - Do not commit `.coverage` files.