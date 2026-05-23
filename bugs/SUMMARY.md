# YachtPlus Backend Bug Hunt Summary

## 1. Stack-Übersicht
- **Sprache:** Python 3.11/3.12 (Backend), TypeScript/Vue (Frontend)
- **Framework:** FastAPI
- **DB:** SQLite (via SQLAlchemy 2)
- **Auth:** JWT (HttpOnly Cookies), pyotp (2FA), bcrypt
- **Einstiegspunkte:** `backend/api/main.py`, Gunicorn hinter Nginx.

## 2. Bug-Statistik
| Severity | Anzahl |
|---|---|
| Critical | 0 |
| High | 2 |
| Medium | 4 |
| Low / Suspicion | 0 |

| Kategorie | Anzahl |
|---|---|
| Auth | 2 |
| Injection | 1 |
| Config | 1 |
| Other (SSRF/REST) | 2 |

## 3. Top-kritischste Bugs
1. **BUG-001 (High):** Container Exec Command Injection. Der WebSocket Endpoint erlaubt es, beliebige Binaries mit Argumenten im Container-Kontext via `shlex.split` auszuführen, statt nur vordefinierte Shells.
2. **BUG-005 (High):** SSRF Fail-Open. DNS Auflösungsfehler (`gaierror`) werden im URL-Validator ignoriert (`pass`), wodurch SSRF-Checks komplett umgangen werden können, wenn `urllib` den Host danach erfolgreich anders auflöst (DNS Rebinding/Custom DNS).
3. **BUG-002 (Medium):** JWT Refresh Auth Bypass. Der `/refresh` Endpoint prüft den User-Status in der DB nicht, was gelöschten/gesperrten Accounts erlaubt, endlos neue gültige Tokens zu beziehen.
4. **BUG-006 (Medium):** IP Spoofing Rate Limit Bypass. Die Funktion `_resolve_client_ip` vertraut Headern (`X-Real-IP`) von jeder beliebigen privaten IP. Angreifer im LAN können Rate Limiting umgehen, indem sie den Header bei jedem Login-Versuch ändern.
5. **BUG-003 (Medium):** API Key Deletion via GET. Ein GET-Request löscht API Keys, was REST-Prinzipien verletzt und einen CSRF-Vektor für unbeabsichtigte Löschungen durch Image-Tags etc. öffnet.

## 4. Cluster-Analyse
- **Auth / Security Controls Bypass:** BUG-002 und BUG-006 zeigen, dass an Rändern der Auth-Logik (Refresh-Flow, IP-Rate-Limiting) die Zustandsprüfungen schwach sind. Man vertraut den ankommenden Daten (JWT valid, Private IP valid) zu sehr, ohne die zugrunde liegende Realität gegenzuprüfen.

## 5. Empfohlene Fix-Reihenfolge
1. **BUG-001** (Exec Injection) beheben, da dies direkten Missbrauch im Docker-Netzwerk erlaubt.
2. **BUG-005** (SSRF Fail-Open) beheben. Die Code-Änderung ist trivial (1 Zeile) und schließt einen gefährlichen Vektor.
3. **BUG-002** (JWT Refresh) anpassen, um sicherzustellen, dass ausgemusterte Accounts wirklich tot sind.
4. **BUG-006** und **BUG-003** (Spoofing & REST-Verletzung) beheben.
5. **BUG-004** (Rate Limiting API Keys) kann als Letztes nachgezogen werden.

## 6. Was wurde NICHT geprüft
- Das Vue/Frontend-Projekt wurde in dieser Analyse nicht tiefgehend auf XSS geprüft, da der Fokus auf dem FastAPI-Backend lag.
- Umfangreiche Docker-Compose/Aiodocker-Integrationen wurden nur punktuell auf Injection gesichtet, nicht aber auf Docker-Spezifische Race-Conditions.

## 7. Verwendete Tools & Versionen
- `ruff` v0.15.14
- `bandit` v1.9.4
- `safety` v3.7.0
