# Elite System Auditor Report

## KRITISCHE ALARME (CRITICAL ALARMS)

1.  **Frontend Framework EOL (End of Life)**:
    *   **Problem**: Das Projekt nutzt Vue 2 (`^2.7.16`) und Vuetify 2 (`^2.7.2`). Beide haben ihr End-of-Life (EOL) am 31. Dezember 2023 erreicht.
    *   **Risiko**: Es gibt keine Sicherheitsupdates mehr. XSS-Lücken oder andere Schwachstellen in diesen Bibliotheken bleiben ungepatcht.
    *   **Beweis**: `frontend/package.json`.
    *   **Handlung**: **Sofortige Migration** auf Vue 3 und Vuetify 3 oder ein modernes Framework (React/Svelte) ist zwingend.

2.  **Veraltete Node.js Basis-Image**:
    *   **Problem**: Das `Dockerfile` nutzte `node:16-alpine`. Node 16 ist EOL seit September 2023.
    *   **Risiko**: Enthält hunderte bekannter Sicherheitslücken (CVEs) im OS-Layer und der Runtime.
    *   **Handlung**: Upgrade auf `node:20-alpine` (Bereits im Fix implementiert).

3.  **Content Security Policy (CSP) Schwachstelle**:
    *   **Problem**: `backend/api/main.py` setzt `script-src ... 'unsafe-eval'`.
    *   **Risiko**: Ermöglicht Code-Injection-Angriffe. Dies ist eine direkte Folge der Vue 2 Nutzung (Runtime Compiler).
    *   **Handlung**: Migration zu Vue 3 (Composition API & Vite) ermöglicht das Entfernen von `unsafe-eval`.

## SYSTEM-BREMSEN (SYSTEM BRAKES)

1.  **Ineffizientes Dashboard Polling**:
    *   **Problem**: `Home.vue` pollt `/api/dashboard/stats` und `/api/containers/stats` alle 2 Sekunden.
    *   **Impact**: Erzeugt unnötige Last auf dem Backend und Netzwerk, skaliert schlecht bei vielen Containern.
    *   **Handlung**: Umstellung auf Server-Sent Events (SSE) (Bereits im Fix implementiert).

2.  **Synchrones Docker-Client Management**:
    *   **Problem**: Im Dashboard-SSE Loop wurde der Docker-Client bei jeder Iteration neu instanziiert.
    *   **Impact**: Overhead durch ständigen Verbindungsaufbau zum Docker Socket.
    *   **Handlung**: Client-Wiederverwendung (Reuse) implementieren (Wird im aktuellen Plan behoben).

## ARCHITEKTUR-SÜNDEN (ARCHITECTURE SINS)

1.  **Code-Duplizierung**:
    *   **Problem**: Logik zur Berechnung von Container-CPU/RAM existierte sowohl im Router als auch im neuen SSE-Modul.
    *   **Impact**: Wartungsalbtraum. Änderungen an der Metrik-Berechnung müssen an zwei Orten erfolgen.
    *   **Handlung**: Refactoring in eine zentrale `actions`-Funktion (DRY-Prinzip).

2.  **Vermischung von UI und Logik**:
    *   **Problem**: Backend liefert teilweise UI-spezifische Strukturen (Templates).
    *   **Impact**: Frontend sollte die Darstellung bestimmen, Backend nur Daten liefern.

---

## AUTONOME ROADMAP

1.  **Refactoring (Sofort)**: Extrahiere `calculate_container_stats` in `backend/api/actions/containers.py` und nutze sie in REST und SSE Endpoints.
2.  **Performance (Sofort)**: Fixiere den Docker-Client Instanziierungs-Bug im SSE Loop.
3.  **Migration (Mittelfristig)**: Starte die Vue 3 Migration. Ersetze Options API durch Composition API schrittweise.
4.  **Security (Laufend)**: Entferne `unsafe-eval` aus CSP nach Abschluss der Frontend-Migration.
