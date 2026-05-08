# Repository Knowledge Base (Jules Context)

## 🏗️ Architecture & Stack
- **Core Stack:** Vue 3 (Vite), FastAPI (Python), SQLite/SQLAlchemy, Docker.
- **Architecture Pattern:** Decoupled SPA (Single Page Application) frontend communicating with a RESTful FastAPI backend. The application acts as a container management UI, directly interacting with the Docker daemon socket (`/var/run/docker.sock`).
- **Key Dependencies:**
  - **Frontend:** Vuetify 3 (UI framework), Pinia & Vuex (State Management), Axios (Data fetching), Vee-Validate 4 (Form validation), vue-chartjs & Chart.js (Charts).
  - **Backend:** FastAPI, SQLAlchemy (ORM), Pydantic (Validation & Settings), Uvicorn (ASGI server), aiodocker/docker (Docker API clients).

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
- **Data Fetching:** Always use Axios via the pre-configured instance (`axios.defaults.baseURL` is set to include `/api`). Independent API requests during initial loading should be executed concurrently using `Promise.all()` to optimize performance.
- **Form Validation:** Use `vee-validate` v4 components (`<Form>`, `<Field>`) with global rules defined in `main.js`.
- **Date Handling:** `dayjs` is strictly for global Vue date formatting (`$formatDate` and `$timeAgo` via `VueUtils`), while `date-fns` is strictly maintained for the `chartjs-adapter-date-fns` integration.
- **Error Handling:** Backend throws FastAPI `HTTPException`. Frontend catches these via Axios interceptors, specifically one that handles token refreshes.
- **Accessibility:** Icon-only buttons (like Vuetify `<v-btn icon>`) must always include descriptive `aria-label` and `title` attributes.
- **Performance:** Synchronous DB calls within async backend endpoints (like unified search) must be wrapped in `fastapi.concurrency.run_in_threadpool` to avoid event-loop starvation.
- **Security & Setup:**
  - **Strict CSP:** Implemented in `main.py` middleware without `unsafe-eval`.
  - **IP Restrictions:** Robust SSRF and IP restriction checks (`is_private_ip`) explicitly verify loopback, link-local, multicast, and `0.0.0.0` in addition to `.is_private`.
  - **Setup Enforcement:** The setup status is enforced dynamically via middleware. Bypass checks ensure bypass is only possible if zero users exist.
  - **Auth Cookies:** Setup endpoints use `HttpOnly` access cookies set via `Authorize.set_access_cookies`.

## 🧪 Testing & Commands
- **Test Runner:**
  - **Frontend:** Vitest. Run using `cd frontend && pnpm vitest run`.
  - **Backend:** Pytest (with `pytest-asyncio` for async and `unittest.mock` for dependencies). Run using `cd backend && DATABASE_URL=sqlite:///:memory: PYTHONPATH=. python3 -m pytest tests/`.
  - **E2E/Frontend UI Verifications:** Playwright Python scripts run against a local preview server (`cd frontend && pnpm run preview` on port 4173).
- **Key Commands:**
  - **Frontend Build/Dev:** `cd frontend && pnpm install && pnpm build` (Strictly `pnpm`, no `npm` or `yarn`), `cd frontend && pnpm dev`.
  - **Backend Dev:** `cd backend && python3 main.py` (after pip install).