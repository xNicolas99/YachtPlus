# SECURITY AUDIT REPORT - YACHT PLUS (DEC 2025)

**AUDITOR:** ELITE SYSTEM AUDITOR (Jules)
**TARGET:** YachtPlus Repository
**DATE:** December 2025

---

## 1. KRITISCHE ALARME (CRITICAL ALARMS)
*Immediate security risks or total failures.*

### **[CRITICAL] Vue.js 2 End-Of-Life (EOL)**
*   **Status:** **DEAD**. Vue 2 reached EOL on December 31, 2023.
*   **Risk:** The frontend framework receives **NO security updates**. Any XSS or prototype pollution vulnerability found in Vue 2 or its ecosystem (Vuetify 2) remains unpatched forever.
*   **Recommendation:** **IMMEDIATE MIGRATION** to Vue 3 + Vuetify 3 or Vite. This is a massive technical debt.

### **[CRITICAL] Authentication Bypass in Setup Flow**
*   **Status:** **VULNERABLE**.
*   **Risk:** The `/api/setup/register` endpoint issues a valid JWT `access_token` immediately upon user creation, *before* 2FA is enforced in `/finalize`.
*   **Exploit:** An attacker can register, receive the token, abort the setup (skipping 2FA), and use the token to access the full API as an Admin.
*   **Fix:** Enforce setup completion checks in the authentication middleware. (Patched in this audit session).

### **[CRITICAL] Docker Socket Exposure**
*   **Status:** **INHERENT RISK**.
*   **Risk:** The application requires `/var/run/docker.sock` to function. If the application is compromised (e.g., via the Vue 2 vulnerabilities), the attacker gains **ROOT ACCESS** to the host system.
*   **Mitigation:** Ensure the app runs as a non-root user (`appuser`) inside the container (Verified: `Dockerfile` and `start.sh` handle this), but the socket access still grants privilege escalation potential.

---

## 2. SYSTEM-BREMSEN (SYSTEM BRAKES)
*Performance bottlenecks and bloat.*

### **[BRAKE] Legacy Build System (Webpack / Vue CLI 4)**
*   **Status:** **SLOW**.
*   **Impact:** Development server startup and HMR (Hot Module Replacement) are significantly slower than modern standards (Vite). Production build artifacts are larger than necessary.
*   **Recommendation:** Migrate build toolchain to Vite.

### **[BRAKE] Synchronous Docker SDK Usage**
*   **Status:** **SUB-OPTIMAL**.
*   **Impact:** While `aiodocker` is used for most operations, legacy code in `backend/api/actions/compose.py` uses the synchronous `docker` library and `sh` module.
*   **Mitigation:** These calls are currently handled by FastAPI's threadpool (via `def` routes), so they don't block the event loop, but they consume thread resources unnecessarily.

---

## 3. ARCHITEKTUR-SÜNDEN (ARCHITECTURE SINS)
*Design and code quality failures.*

### **[SIN] Hardcoded Configuration**
*   **Status:** **MESSY**.
*   **Issue:** `BASE_TEMPLATE_VARIABLES` were hardcoded in `backend/api/settings.py`, mixing code with configuration.
*   **Fix:** Extracted to `backend/api/db/base_template_variables.json`. (Patched in this audit session).

### **[SIN] SQLAlchemy < 2.0**
*   **Status:** **LEGACY**.
*   **Issue:** The project pins `SQLAlchemy<2.0`. This prevents using modern ORM features and optimizations available in SQLAlchemy 2.0+.

---

## AUTONOMOUS ROADMAP (FOR FIXER AGENT)

1.  **REVERT** strict `ALLOWED_HOSTS` default (Done - breaks LAN usage).
2.  **VERIFY** Setup Bypass Middleware:
    *   Ensure `/api/setup`, `/api/auth` are accessible.
    *   Ensure `/api/apps` is BLOCKED if setup is incomplete.
3.  **CLEANUP** Configuration:
    *   Validate `base_template_variables.json` loading.
4.  **FUTURE (Major)**:
    *   `npm install -g create-vue` -> Begin Vue 3 Migration.
    *   Update `backend/requirements.txt` to allow `SQLAlchemy>=2.0` and refactor models.
