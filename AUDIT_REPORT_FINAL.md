# ELITE SYSTEM AUDIT REPORT: YACHT-PLUS

**DATUM:** 28.12.2025
**AUDITOR:** JULES (Elite System Auditor)
**STATUS:** KRITISCH
**STACK:** Python 3.11 (FastAPI), Vue 3 (Vite), Docker

---

## 1. TECH-STACK & ANALYSE
Das System ist ein Docker-Container-Management-Dashboard.
*   **Backend:** FastAPI (Async), Uvicorn, Gunicorn. Nutzt `aiodocker` für Async-Ops und `docker` (Python SDK) via `subprocess`/`run_in_thread` für Legacy-Ops.
*   **Frontend:** Vue 3 Migration (Vite), Vuetify 3. Node 20.
*   **Infrastruktur:** Läuft als Non-Root (`appuser`, UID 1000). Nginx Reverse Proxy.

---

## 2. KRITISCHE ALARME (Sofortiges Handeln erforderlich)

### 🚨 DIE "STUB"-LÜGE (Betrug am Compiler)
Der Audit hat ergeben, dass die Migration auf Vue 3 eine Fassade ist. In `frontend/vite.config.js` werden kritische Bibliotheken auf leere "Stubs" umgeleitet:
*   `vee-validate` -> `src/stubs/vee-validate.js`
*   `vue-chartjs` -> `src/stubs/vue-chartjs.js`
*   `vue-chat-scroll` -> `src/stubs/vue-chat-scroll.js`
*   `vue2-ace-editor` -> `src/stubs/vue2-ace-editor.js`

**Konsequenz:** Validierungen, Charts und Editoren existieren im Build, sind aber funktional tot. Das System täuscht Funktionalität vor. Das widerspricht direkt den angeblichen Fixes aus dem Dezember-Audit.

### 🚨 CSP-HINTERTÜR: `unsafe-eval`
In `backend/api/main.py` wird `script-src 'unsafe-eval'` explizit erlaubt.
*   **Code:** `script-src 'self' 'unsafe-eval' 'unsafe-inline'`
*   **Risiko:** Dies öffnet Tür und Tor für XSS-Angriffe. In einer modernen Vue 3 (Vite) Applikation ist `unsafe-eval` NICHT notwendig. Das ist ein gefährliches Überbleibsel der Vue 2 Webpack-Ära.

### 🚨 ALLOWED_HOSTS WILDCARD
`backend/api/settings.py` erlaubt standardmäßig `ALLOWED_HOSTS=["*"]`.
*   **Risiko:** Host-Header-Injection-Angriffe sind möglich. In Production darf dies niemals der Default sein.

---

## 3. SYSTEM-BREMSEN (Performance-Killer)

### 🐌 DOPPELTE DOCKER-LAST
Das Backend lädt ZWEI Docker-Clients:
1.  `aiodocker` (Async, genutzt in `main.py`)
2.  `docker` (Sync Python SDK, genutzt in `actions/compose.py`)
**Urteil:** Verschwendung von RAM und CPU-Zyklen. Die `docker`-Bibliothek ist synchron und blockiert. Sie wird zwar in Threads ausgelagert, aber das erhöht den Context-Switching-Overhead unnötig.

### 🐌 ZOMBIE-DEPENDENCY: MOMENT.JS
In `frontend/package.json` ist `moment` gelistet, obwohl das Projekt angeblich auf `dayjs` (via Memory/Plugins) umgestiegen ist.
**Urteil:** Moment.js ist deprecated und bläht das Bundle unnötig auf (kein Tree-Shaking).

### 🐌 SYNCHRONE REQUESTS
`backend/requirements.txt` listet `requests`. In einem Async-Framework wie FastAPI sollte ausschließlich `httpx` oder `aiohttp` genutzt werden. Synchrone Aufrufe in einer Async-Loop (selbst wenn theoretisch isoliert) sind eine tickende Zeitbombe für die Performance unter Last.

---

## 4. ARCHITEKTUR-SÜNDEN (Code-Qualität)

### 💀 SPAGHETTI-IMPORTS IN MIDDLEWARE
In `backend/api/main.py` wird innerhalb der Middleware-Funktion `check_setup_status` importiert:
`from api.routers.setup.setup import is_setup_completed`
**Urteil:** Das umgeht Circular Dependency Fehler durch schlechtes Design. Die Setup-Logik sollte entkoppelt sein (z.B. in einen Service oder State-Manager), um saubere Top-Level-Imports zu ermöglichen.

### 💀 INKONSISTENTE API-STRUKTUR (Dashboard)
Der Router `backend/api/routers/dashboard.py` liefert nur `/stats`. Die modernen "Live-Updates" via SSE (Server-Sent Events), die in `Home.vue` erwartet werden, fehlen im Router-File oder sind schlecht abstrahiert.

---

## AUTONOME ROADMAP (Für den Fixer-Agent)

Du wirst die folgenden Schritte exakt in dieser Reihenfolge ausführen. Melde keinen Erfolg, bis die Stubs eliminiert sind.

1.  **STUB-ELIMINIERUNG (Frontend):**
    *   Lösche die Alias-Einträge in `frontend/vite.config.js`.
    *   Installiere echte Vue 3 kompatible Versionen: `vee-validate@4`, `vue-chartjs@5`, `chart.js`.
    *   Passe den Import-Code in den Komponenten an, falls nötig.

2.  **SECURITY-HARDENING (Backend):**
    *   Entferne `'unsafe-eval'` aus der CSP in `backend/api/main.py`.
    *   Setze `ALLOWED_HOSTS` defaultmäßig auf `localhost` oder die Docker-IP, nicht `*`.

3.  **CLEANUP (Dependencies):**
    *   Entferne `moment` aus `frontend/package.json`.
    *   Entferne `requests` aus `backend/requirements.txt` (ersetze durch `httpx` wo nötig).

4.  **REFACTORING (Architektur):**
    *   Verschiebe `is_setup_completed` in `backend/api/utils/setup_status.py` (neue Datei), um den Circular Import in `main.py` zu lösen.

5.  **VERIFICATION:**
    *   Führe `npm build` aus. Es darf keine Fehler geben.
    *   Starte das Backend. Es darf keine Import-Fehler geben.

**AUSFÜHREN.**
