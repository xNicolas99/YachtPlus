# ELITE SYSTEM AUDIT REPORT - DEZEMBER 2025

**DATUM:** 28.12.2025
**STATUS:** KRITISCH
**AUDITOR:** JULES (ELITE SYSTEM AUDITOR)

---

## 1. TECH-STACK-SCAN & ANALYSE

*   **Backend:** Python 3.11 (FastAPI, Uvicorn, Gunicorn, Aiodocker).
*   **Frontend:** Vue 3 (Vite, Vuetify), aber mit massiven Altlasten aus Vue 2.
*   **Deployment:** Docker Container (Rootless `appuser`, aber mit potenziellen Privileg-Eskalationspfaden durch Socket-Mounts).
*   **Zweck:** Docker Management Dashboard (Yacht-Fork/Rewrite).

---

## 2. AGGRESSIVE AUDIT (DIE ABRECHNUNG)

### 🚨 KRITISCHE ALARME (SOFORTIGE HANDLUNG ERFORDERLICH)

**1. CONTENT SECURITY POLICY (CSP) SABOTAGE**
In `backend/api/main.py` wird der Header `Content-Security-Policy` explizit mit `unsafe-eval` gesetzt.
*   **Der Beweis:** `script-src 'self' 'unsafe-eval' 'unsafe-inline';`
*   **Die Ausrede im Code:** "REQUIRED for Vue 2 runtime template compilation."
*   **Die Realität:** Das Projekt nutzt Vite und Vue 3. Es gibt **keinen** Grund für `unsafe-eval`, außer Faulheit bei der Migration. Dies öffnet Tür und Tor für Cross-Site-Scripting (XSS).
*   **Referenz:** [MDN: CSP script-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy/script-src)

**2. ARCHITEKTONISCHE LÜGE: "FAKE STUBS"**
Die Datei `frontend/vite.config.js` ist ein Verbrechen an der Software-Integrität.
*   **Der Befund:** Kritische Bibliotheken wie `vee-validate` (Input Validierung!) werden auf leere Dateien (`src/stubs/vee-validate.js`) umgeleitet.
*   **Die Konsequenz:** Formular-Validierung im Frontend existiert faktisch nicht. Der Build läuft durch, aber die Anwendung ist funktionaler Schrott. Das ist kein "Refactoring", das ist Täuschung.

**3. VUE 3 INKOMPATIBILITÄT (RUNTIME CRASH)**
In `frontend/src/plugins/vueutils.js` wird `Vue.filter` verwendet.
*   **Der Fehler:** `Vue.filter` wurde in Vue 3 ersatzlos gestrichen.
*   **Das Ergebnis:** Die Anwendung wird beim Start crashen ("TypeError: Vue.filter is not a function"). Der Code wurde blind kopiert, nicht migriert.
*   **Referenz:** [Vue 3 Migration Guide: Filters](https://v3-migration.vuejs.org/breaking-changes/filters.html)

**4. UNSICHERE DEFAULTS (HOST HEADER ATTACKS)**
In `backend/api/settings.py` ist `ALLOWED_HOSTS` standardmäßig auf `["*"]` gesetzt.
*   **Das Risiko:** Erlaubt Cache-Poisoning und Passwort-Reset-Angriffe via Host-Header-Manipulation. In einer "Elite"-Umgebung darf der Default niemals `*` sein, oder muss zumindest im Docker-Kontext strikt gewarnt werden (was `main.py` zwar tut, aber nicht blockiert).

---

### 🐢 SYSTEM-BREMSEN (PERFORMANCE & BLOAT)

**1. "MOMENT.JS" LEICHE**
`frontend/package.json` und `frontend/src/plugins/vueutils.js` nutzen `moment`.
*   **Das Urteil:** Moment.js ist im "Maintenance Mode" und bekannt für riesige Bundle-Sizes.
*   **Die Lösung:** `dayjs` ist moderner, kleiner (2kB vs 60kB+) und API-kompatibel. Die Migration wurde begonnen (siehe globale Properties), aber `vueutils.js` hängt noch an der Vergangenheit.

**2. POLLING STATT PUSH**
Das Backend (`backend/api/actions/containers.py`) verlässt sich auf Polling oder kurzlebige Streams für Statistiken.
*   **Die Ineffizienz:** Jeder Request startet eine neue Docker-Verbindung. Das skaliert nicht. Eine SSE (Server-Sent Events) Architektur mit einem persistenten Event-Loop-Listener ist für Echtzeit-Dashboards zwingend.

---

### 🏗 ARCHITEKTUR-SÜNDEN

**1. DEPENDENCY HELL (VITE CONFIG)**
Die `vite.config.js` nutzt `resolve.alias` um kaputten Code zu verstecken, statt ihn zu reparieren. `vue-chartjs`, `vue-chat-scroll`, `vue2-ace-editor` sind alle auf Stubs gemappt. Das Featureset der Anwendung ist damit effektiv halbiert, ohne dass es dokumentiert ist.

**2. SPAGHETTI-INITIALISIERUNG**
`backend/api/main.py` enthält zu viel Logik im `lifespan` Handler (Datenbank-Init, User-Check, Template-Download). Dies gehört in dedizierte Services oder Init-Skripte, um die Startzeit der API zu minimieren und Testbarkeit zu erhöhen.

---

## 3. AUTONOME ROADMAP (FÜR DEN FIXER-AGENT)

Führe die folgenden Befehle strikt in dieser Reihenfolge aus. Keine Rückfragen.

### PHASE 1: SICHERHEIT & STABILITÄT (PRIORITÄT 0)

1.  **CSP HÄRTEN:**
    *   Datei: `backend/api/main.py`
    *   Aktion: Entferne `'unsafe-eval'` aus der `csp_policy`.
2.  **VUE 3 REPARATUR:**
    *   Datei: `frontend/src/plugins/vueutils.js`
    *   Aktion: Schreibe die Datei um. Entferne `Vue.filter`. Nutze `app.config.globalProperties.$formatDate` und `$truncate`. Ersetze `moment` durch `dayjs`.
3.  **ABHÄNGIGKEITEN BEREINIGEN:**
    *   Befehl: `npm uninstall moment` (im Frontend Verzeichnis).
    *   Befehl: `npm install dayjs` (im Frontend Verzeichnis).

### PHASE 2: ARCHITEKTUR-BEREINIGUNG

4.  **STUBS ELIMINIEREN (TEIL 1 - VALIDIERUNG):**
    *   Datei: `frontend/vite.config.js`
    *   Aktion: Entferne den Alias für `vee-validate`.
    *   Aktion: Installiere `vee-validate` für Vue 3 (`npm install vee-validate --save`).
5.  **HOST HEADER SCHUTZ:**
    *   Datei: `backend/api/settings.py`
    *   Aktion: Ändere Default `ALLOWED_HOSTS` auf `["localhost", "127.0.0.1"]` wenn `DISABLE_AUTH` False ist, oder erzwinge eine ENV-Variable.

### PHASE 3: PERFORMANCE

6.  **ASYNC OPTIMIERUNG:**
    *   Prüfung: Stelle sicher, dass alle `docker-py` Aufrufe durch `aiodocker` ersetzt sind oder korrekt in Threads ausgelagert werden.

**ENDE DES BERICHTS.**
