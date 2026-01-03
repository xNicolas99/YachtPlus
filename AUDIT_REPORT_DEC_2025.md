# AUDIT REPORT: YACHT-PLUS (DECEMBER 2025)

**AUDITOR:** ELITE SYSTEM AUDITOR (JULES)
**DATE:** DECEMBER 2025
**STATUS:** CRITICAL FAILURES DETECTED

---

## 🚨 KRITISCHE ALARME (SOFORTIGE SICHERHEITSRISIKEN)

### 1. END-OF-LIFE (EOL) TECHNOLOGY STACK
Das Fundament des Projekts besteht aus toter Technologie. Dies ist kein "Wartungsproblem", sondern grobe Fahrlässigkeit.
*   **Vue 2 (v2.6/2.7)**: EOL seit **31. Dez. 2023**. Es gibt keine Sicherheitspatches mehr. Jede XSS-Lücke im Framework bleibt für immer offen.
*   **Vuetify 2**: EOL. Inkompatibel mit modernen Ökosystemen.
*   **Node 16**: EOL seit **Sep 2023**. Die Nutzung in der Build-Pipeline ist ein Sicherheitsrisiko.

**Risiko**: Kritisch. Hohe Wahrscheinlichkeit für nicht patchbare CVEs.

### 2. AUTHENTICATION BYPASS MECHANISMUS (`DISABLE_AUTH`)
In `backend/api/settings.py` existiert die Variable `DISABLE_AUTH`:
```python
DISABLE_AUTH: bool = os.environ.get("DISABLE_AUTH", "False").lower() == "true"
```
Wird diese Variable in Produktion versehentlich auf `true` gesetzt, ist die **Authentifizierung vollständig deaktiviert**. Jeder mit Netzwerkzugriff erhält vollen Root-Zugriff (via Docker Socket). Diese "Entwickler-Bequemlichkeit" ist eine Hintertür.

**Risiko**: Kritisch. Totale Systemkompromittierung.

### 3. UNSICHERE CONTENT SECURITY POLICY (CSP)
Die Anwendung aktiviert explizit `'unsafe-eval'` im CSP-Header in `backend/api/main.py`:
```python
script-src 'self' 'unsafe-eval' 'unsafe-inline';
```
Dies ist für Vue 2 notwendig, ermöglicht aber Angreifern das Ausführen von beliebigem Code bei Injection-Lücken.

**Risiko**: Hoch.

---

## 🐢 SYSTEM-BREMSEN (PERFORMANCE KILLER)

### 1. DASHBOARD POLLING STATT SSE
Das Dashboard nutzt Client-Side Polling, um Container-Statistiken abzurufen.
*   **Auswirkung**: Alle paar Sekunden wird eine neue HTTP-Verbindung geöffnet. Das Backend muss bei jedem Aufruf `aiodocker` neu instanziieren oder API-Calls feuern.
*   **Urteil**: Unnötiger Netzwerk-Overhead und CPU-Last. Das Backend unterstützt bereits `sse-starlette`. Statistiken müssen via Server-Sent Events (SSE) gepusht werden.

### 2. MONSTRÖSE FRONTEND BUNDLES
Die Nutzung von **Vuetify 2** führt zu riesigen CSS/JS Bundles. Moderne Frameworks (Vue 3 + Vite) bieten Tree-Shaking, das die Größe um 70-90% reduziert. Hier werden Megabytes an ungenutztem Material-Design-Code geladen.

---

## 🏗️ ARCHITEKTUR-SÜNDEN (DESIGN FEHLER)

### 1. "GOD" OBJECTS IM VUE STORE
In `frontend/src/store/modules/auth.js` werden komplette Axios-Response-Objekte in den State geschrieben:
```javascript
commit(AUTH_SUCCESS, resp);
```
Vuex/Pinia State darf nur serialisierbare Daten (JSON) enthalten. Das Speichern komplexer Objekte bricht Time-Travel-Debugging und verursacht Memory Leaks.

### 2. SYNC/ASYNC VERMISCHUNG
Das Backend importiert `docker.errors` (synchron) in `main.py`, während `aiodocker` (asynchron) genutzt wird.
*   **Risiko**: Sobald synchroner Docker-Client-Code in einer `async def` Funktion ausgeführt wird, **blockiert dies den gesamten Event Loop** und friert den Server für alle User ein.

### 3. FRAGILE SETUP LOGIK
Die Setup-Middleware prüft URL-Präfixe (`/setup`, `/auth`). Diese String-Matching-Methode ist zerbrechlich. Änderungen an der Nginx-Konfiguration können dazu führen, dass geschützte Endpunkte offen liegen.

---

## 🤖 AUTONOME ROADMAP (FIXER INSTRUCTIONS)

**PHASE 1: HARDENING (SOFORT)**
1.  **Backdoor Entfernen**: Lösche die `DISABLE_AUTH` Logik aus `backend/api/settings.py` und `backend/api/main.py`.
2.  **CSP Sanitizing**: Dokumentiere `unsafe-eval` als Blocker für die Migration.
3.  **Docker Socket Audit**: Stelle sicher, dass `backend/start.sh` Zugriffsrechte restriktiv setzt.

**PHASE 2: MODERNISIERUNG (KURZFRISTIG)**
1.  **Build Pipeline Upgrade**: Aktualisiere `Dockerfile` auf `node:20-alpine` (oder aktuelle LTS).
2.  **Linting**: Erzwinge striktes Linting im Backend, um blockierendes I/O zu finden.

**PHASE 3: DIE GROSSE MIGRATION (MITTELFRISTIG)**
1.  **Vue 3 Rewrite**:
    *   Neues Vue 3 + Vite Projekt parallel aufsetzen.
    *   Komponenten portieren, Vuetify durch leichtgewichtige Alternative ersetzen.
    *   Vuex durch Pinia ersetzen.
2.  **Stats Refactoring**: Implementiere SSE-Endpunkt für Dashboard-Stats (`/api/stats/stream`) und entferne Polling.

**BEFEHLE FÜR DEN NÄCHSTEN AGENTEN:**
```bash
# 1. Entferne DISABLE_AUTH (Sicherheit zuerst)
sed -i '/DISABLE_AUTH/d' backend/api/settings.py
sed -i '/DISABLE_AUTH/d' backend/api/main.py

# 2. Erstelle Migrationsplan-Datei
touch MIGRATION_PLAN_2025.md
```
