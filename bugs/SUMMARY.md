# Bug Hunt Summary

## Stack-Übersicht

- **Frontend**: Vue 3.4, Vite 5, Vuetify 3, Pinia + Vuex 4, vee-validate v4.
- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2, aiodocker, APScheduler.
- **Datenbank**: SQLite by default (`/config/yacht.db`), Postgres/MySQL supported.
- **Authentifizierung**: JWT in HttpOnly cookies, mandatory 2FA (TOTP), bcrypt password hashing, slowapi rate limiting.
- **Build-Tool**: Vite (Frontend), Docker (Single Container, Nginx + Gunicorn).
- **Test-Framework**: pytest (Backend).

## Bug-Statistik

| Severity | Anzahl |
|---|---|
| Critical | 1 |
| High | 0 |
| Medium | 0 |
| Low | 3 |
| Suspicion | 0 |

| Kategorie | Anzahl |
|---|---|
| Injection | 1 |
| Config | 1 |
| ErrorHandling | 1 |
| Logging / Other | 1 (False Positive) |

## Top-5-kritischste Bugs

1. **BUG-003-cmd-injection**: `api/actions/compose.py` reicht Parameter unvalidiert an `subprocess.run` mit `docker-compose` durch.

## Cluster-Analyse

- **BUG-005-bare-except-containers**: Fehlerhaftes (zu weites) Exception-Handling in Container-Actions.
- **BUG-004-missing-compose-dir-env**: Konfigurationsfehler in `api/settings.py`, der zu Folgefehlern beim Laden der `COMPOSE_DIR` in Compose-Actions führt.
- *Kein gemeinsamer Root Cause, aber BUG-004 und BUG-003 betreffen dasselbe Compose-Subsystem.*

## Empfohlene Fix-Reihenfolge

1. **BUG-003** (Critical): Die Injection Vulnerability muss sofort behoben werden.
2. **BUG-004** (Low): Da dies eine zentrale Config ist, welche Funktionalitäten lahmlegt, sollte es früh behoben werden.
3. **BUG-005** (Low): Kosmetische Code-Qualitätsverbesserung und zur besseren Fehlerdiagnose nützlich.

## Was wurde NICHT geprüft

- **Frontend Code**: Da die node_modules fehlten (oder npm/vite nicht installiert waren) konnte der Frontend-Code nicht vollständig auf Type-Sicherheit und Bundling-Bugs gescannt werden.
- **Komplette Race-Conditions bei der Setup-Logik**: Zeit/Zugriffsgründe verhinderten detaillierte concurrency-tests beim TOTP Setup.

## Verwendete Tools & Versionen

- **semgrep**: 1.163.0
- **bandit**: 1.9.4
- **flake8**: 7.3.0
- **grep/bash utilities**
