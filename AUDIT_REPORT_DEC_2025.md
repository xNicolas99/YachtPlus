# ELITE AUDIT REPORT - YACHT PLUS (DEZEMBER 2025)

**AUDITOR:** JULES (Elite System Auditor)
**DATUM:** 2025-12-01
**STATUS:** **KRITISCH**

Dieses Dokument ist das Ergebnis einer gnadenlosen Tiefenanalyse des YachtPlus Repositories. Es deckt massive Sicherheitslücken, veraltete Technologien und Design-Fehler auf, die das Projekt existenziell gefährden.

---

## 1. KRITISCHE ALARME (Sofortiger Handlungsbedarf)

Hier sind die Fehler, die das Projekt anfällig für Angriffe machen oder die Betriebsfähigkeit beenden.

### 🚨 ALARM 1: Zombie-Frontend (Vue 2 & Vuetify 2)
**Status:** **EOL seit Dezember 2023**
Der Frontend-Stack ist seit zwei Jahren tot.
-   **Framework:** `vue: ^2.7.16`. Vue 2 hat das "End of Life" am 31.12.2023 erreicht. Es gibt **keine Sicherheitsupdates** mehr.
-   **UI-Bibliothek:** `vuetify: ^2.7.2`. Ebenfalls EOL.
-   **Risiko:** Ungepatchte XSS-Lücken im Framework selbst. Browser-Inkompatibilitäten.
-   **Beweis:** [Vue 2 EOL Announcement](https://v2.vuejs.org/lts/)

### 🚨 ALARM 2: Infrastruktur-Verwesung (Node 16 Base Image)
**Status:** **EOL seit September 2023**
Das `Dockerfile` verwendet `FROM node:16-alpine as build-stage`.
-   **Risiko:** Node 16 erhält keine Sicherheitsupdates mehr. Die Build-Umgebung ist voller bekannter CVEs.
-   **Konsequenz:** Ein kompromittierter Build-Container kann Malicious Code in das Frontend injizieren (Supply Chain Attack).
-   **Beweis:** [Node.js EOL Schedule](https://endoflife.date/nodejs)

### 🚨 ALARM 3: CSP Schwachstelle ('unsafe-eval')
**Status:** **UNSICHER**
In `backend/api/main.py` wird die Content Security Policy (CSP) definiert:
```python
script-src 'self' 'unsafe-eval' 'unsafe-inline';
```
-   **Grund:** Vue 2 benötigt `unsafe-eval` für den Runtime-Compiler.
-   **Risiko:** `unsafe-eval` hebelt den primären Schutz von CSP gegen Cross-Site Scripting (XSS) aus. Ein Angreifer, der JS injizieren kann, kann beliebigen Code ausführen.
-   **Lösung:** Migration zu Vue 3 (Composition API) und Vite, was `unsafe-eval` überflüssig macht.

---

## 2. SYSTEM-BREMSEN (Performance-Killer)

Diese Komponenten verschwenden Ressourcen und ruinieren die User Experience.

### 🛑 BREMSE 1: Legacy Build System (Webpack)
Das Frontend nutzt `@vue/cli-service` (Webpack-basiert).
-   **Problem:** Langsame Build-Zeiten, riesige Bundles, ineffizientes Tree-Shaking.
-   **Benchmark 2025:** Vite ist 10-100x schneller im Dev-Mode und produziert optimiertere Production-Builds. Webpack in einem neuen Projekt zu nutzen, ist Fahrlässigkeit.

### 🛑 BREMSE 2: Dashboard Polling
Das Dashboard (`Home.vue`) pollt Container-Statistiken alle 2 Sekunden via `setInterval`.
-   **Ineffizienz:** Erzeugt unnötige Netzwerklast und CPU-Spikes auf dem Backend, selbst wenn sich nichts ändert.
-   **Lösung:** Server-Sent Events (SSE) oder WebSockets nutzen, die bereits für Logs/Terminals implementiert sind. Das Backend unterstützt SSE (`sse-starlette`), nutzt es aber nicht konsequent für Stats.

---

## 3. ARCHITEKTUR-SÜNDEN (Design-Versagen)

Strukturelle Fehler, die Wartbarkeit und Skalierbarkeit verhindern.

### 💀 SÜNDE 1: Tight Coupling an EOL-Tech
Der gesamte Frontend-Code ist eng mit Vuetify 2 Komponenten (`v-card`, `v-btn` etc.) verdrahtet. Eine Migration zu Vue 3 ist kein Update, sondern ein **Rewrite**, da Vuetify 3 massive Breaking Changes hat. Das Design-Pattern hat keine Abstraktionsschicht für UI-Komponenten.

### 💀 SÜNDE 2: Docker Socket Exposure
Der Container benötigt `/var/run/docker.sock`.
-   **Realität:** Wer den Yacht-Container übernimmt, ist `root` auf dem Host.
-   **Versäumnis:** Es fehlt eine strikte Warnung oder eine Option für Rootless Docker / Docker API Proxy in der Standard-Konfiguration.
-   **Milderung:** `start.sh` nutzt `gosu` für Drop-Privileges, was gut ist, aber der Socket bleibt als Angriffsvektor gemountet.

---

## 4. AUTONOME ROADMAP (Der Rettungsplan)

Folgende Befehle muss der Fixer-Agent in exakt dieser Reihenfolge ausführen, um das Projekt zu retten.

### PHASE 1: Infrastruktur-Rettung
1.  **Update Dockerfile:**
    -   Ändere `FROM node:16-alpine` zu `FROM node:22-alpine` (LTS 2025).
    -   Aktualisiere `python:3.11-slim` auf `python:3.12-slim` oder `3.13` für Performance-Boosts.

### PHASE 2: Backend-Härtung
2.  **Dependency-Update:**
    -   Prüfe `aiodocker` auf Updates oder ersetze es durch den nativen asynchronen Docker-Client (sofern verfügbar und stabil).
    -   Entferne `unsafe-inline` aus der CSP, wo immer möglich (erfordert Frontend-Anpassungen).

### PHASE 3: Frontend-Kernsanierung (Das Großprojekt)
3.  **Migrationsvorbereitung:**
    -   Installiere Vue 3 Migration Build (`@vue/compat`).
4.  **Build-Tool Switch:**
    -   Ersetze Webpack durch **Vite**.
5.  **Rewrite:**
    -   Schreibe Komponenten Stück für Stück auf Vue 3 Composition API (`<script setup>`) um.
    -   Ersetze Vuetify 2 durch Vuetify 3 (oder ein leichtgewichtigeres Framework wie Tailwind + HeadlessUI).

**URTEIL:** Das Projekt ist im aktuellen Zustand (Dez 2025) **NICHT PRODUKTIV EINSETZBAR**. Es ist ein Sicherheitsrisiko. Fix it or delete it.
