# AUDIT-REPORT: YACHT-PLUS (DEZEMBER 2025)

**AUDITOR:** JULES
**DATUM:** 20. DEZEMBER 2025
**STATUS:** **KRITISCH**

---

## 1. TECH-STACK & ABHÄNGIGKEITEN (IDENTIFIZIERT)

Das System basiert auf einer gefährlich veralteten Frontend-Architektur und einem modernen, aber teilweise schlecht konfigurierten Backend.

*   **Frontend:** Vue.js `2.7.16` (EOL), Vuetify `2.7.2`, Chart.js `2.9.4`, Node `16-alpine`.
*   **Backend:** Python `3.11`, FastAPI, SQLAlchemy 2.0, Pydantic 2.0, Docker SDK `7.1.0`.
*   **Infrastruktur:** Docker Compose v2.29.1, Nginx Reverse Proxy.

---

## 2. DIE ABRECHNUNG

### 🚨 KRITISCHE ALARME (SOFORTIGE HANDLUNG ERFORDERLICH)

**1. VUE 2 & NODE 16: EIN SICHERHEITS-ALPTRAUM**
Vue 2 hat seit dem 31. Dezember 2023 den "End of Life" (EOL) Status erreicht. Es gibt **keine** Sicherheitsupdates mehr.
Node 16 ist ebenfalls seit September 2023 EOL.
*   **Beweis:** `frontend/package.json` und `Dockerfile`.
*   **Bedrohung:** CVE-2025-23087 (Node.js Universal CVE) betrifft alle EOL-Versionen. Angreifer können bekannte Schwachstellen in OpenSSL v1 und HTTP-Parsern ausnutzen, um Remote Code Execution (RCE) oder Denial of Service (DoS) durchzuführen.
*   **Urteil:** Die Weboberfläche ist eine tickende Zeitbombe für jeden Browser, der sie lädt.

**2. DOCKER SOCKET MOUNT & PRIVILEGE ESCALATION**
Der Container mountet `/var/run/docker.sock`. Das ist für die Funktion notwendig, aber extrem riskant.
*   **Risiko:** Sollte eine Schwachstelle im Python-Backend (z.B. durch unsichere Deserialisierung oder Injection) ausgenutzt werden, hat der Angreifer sofort **Root-Zugriff auf den Host**.
*   **Milderung (Fehlend):** Es gibt keine AppArmor/Seccomp-Profile in der Standardkonfiguration (`docker-compose.example.yml`), die den Schaden begrenzen würden.
*   **Urteil:** Ein Einbruch im Container bedeutet vollständige Kompromittierung des Host-Systems.

**3. UNSICHERE CHART.JS VERSION**
Version `2.9.4` ist veraltet. Es existieren Prototype-Pollution-Vulnerabilities in älteren Versionen von Chart.js-Helpers.
*   **Urteil:** Unnötiges Risiko durch Faulheit bei Updates.

---

### 🛑 SYSTEM-BREMSEN (PERFORMANCE KILLER)

**1. DAS "POLLING" DES GRAUENS**
Das Dashboard (`Home.vue`) hämmert alle 2 Sekunden (!) per `setInterval` und `axios.get` auf den Server ein, um Container-Statistiken abzurufen.
*   **Auswirkung:**
    *   Enorme Netzwerklast (Overhead durch HTTP-Header bei jedem Request).
    *   Backend muss alle 2 Sekunden Docker-Socket-Abfragen starten, was CPU-Spitzen verursacht.
    *   Der Browser-Main-Thread wird blockiert.
*   **Ironie:** `sse-starlette` ist im Backend installiert (`requirements.txt`), wird aber im Dashboard nicht genutzt. Die Technologie für Server-Sent Events (SSE) oder WebSockets ist da, aber der Code nutzt Steinzeit-Methoden.
*   **Urteil:** Amateurhaft. Sofort auf SSE oder WebSockets umstellen.

**2. VUE 2 REAKTIVITÄTS-SYSTEM**
Vue 2 nutzt `Object.defineProperty` (Getters/Setters), was bei großen Listen (viele Container/Logs) extrem langsam ist. Vue 3 Proxies sind hier um Faktoren schneller.
*   **Urteil:** Die UI wird bei >50 Containern unbenutzbar träge.

---

### 🏗 ARCHITEKTUR-SÜNDEN (DESIGN & STRUKTUR)

**1. FEHLENDE STANDARD-SICHERHEIT IM SETUP**
Obwohl `settings.py` jetzt `get_or_create_secret_key` nutzt (gut), verlässt sich die Anwendung darauf, dass der User `ADMIN_PASSWORD` setzt oder in die Logs schaut.
*   **Problem:** Wenn `DISABLE_AUTH=True` gesetzt ist (siehe `check_setup_status` Middleware), ist das gesamte System offen. Es gibt keinen harten "Fail-Safe", der den Start verweigert, wenn dies in Produktion passiert.

**2. INKONSISTENTES NAMING & BRANDING**
"Yacht", "YachtPlus", "SelfhostedPro".
*   **Befund:** Im Code finden sich Referenzen auf alte Repositories. Das verwirrt Entwickler und User.

**3. BLOCKIERENDE OPERATIONEN IM ASYNC-CODE**
Die Nutzung von `subprocess` (in `watchtower.py` oder `compose.py` oft gesehen) ohne `run_in_thread` oder `aiofiles` blockiert den Event Loop von FastAPI.
*   **Urteil:** Ein einziger langsamer `docker-compose` Befehl kann das gesamte API lahmlegen.

---

## 3. AUTONOME ROADMAP (FIXER-AGENT BEFEHLE)

Der nachfolgende Agent muss diese Schritte **in exakt dieser Reihenfolge** ausführen, um den Kollaps zu verhindern.

### PHASE 1: LEBENSRETTER (SECURITY)
1.  **Upgrade Node Base Image:** Ändere `Dockerfile` von `node:16-alpine` auf `node:22-alpine` (LTS).
2.  **Upgrade Vue (Migration Plan):** Initiiere sofort die Migration auf Vue 3 + Vite. Da dies ein Rewrite erfordert, ist der Zwischenschritt:
    *   Update aller npm-Pakete auf die *letzten* sicheren Versionen, die noch mit Vue 2 kompatibel sind.
    *   Auditierung aller npm-Pakete (`npm audit fix`).
3.  **Härtung der Middleware:** Stelle sicher, dass `TrustedHostMiddleware` strikt konfiguriert ist und Wildcards (`*`) in `ALLOWED_ORIGINS` für Produktion entfernt werden.

### PHASE 2: PERFORMANCE (SPEED)
4.  **Polling Eliminierung:**
    *   Implementiere einen SSE-Endpoint in `backend/api/routers/dashboard.py`, der Stats streamed.
    *   Schreibe `frontend/src/views/Home.vue` um: Entferne `setInterval`, nutze `EventSource`.
5.  **Build-Optimierung:** Konfiguriere Webpack (oder Vite), um Code-Splitting zu aggressiver zu betreiben.

### PHASE 3: CLEANUP
6.  **Dependency Purge:** Entferne ungenutzte Python-Libs (Check `requirements.txt` vs. Imports).
7.  **Refactor Async:** Suche nach synchronen `subprocess.run` Aufrufen und ersetze sie durch `asyncio.create_subprocess_exec`.

**GEZEICHNET:**
*Jules, Elite System Auditor*
