# SECURITY-AUDIT.md — Code-Audit YachtPlus

## Zusammenfassung

- Audit-Datum: 2026-08-21
- Baseline-Commit: `ee7fe6e`
- Backend-Tests: 501 grün
- Frontend-Tests: 21 grün
- pip-audit (backend venv): 0 bekannte Vulnerabilities
- npm audit (frontend): 0 Vulnerabilities

## Befundregister

### CRITICAL

(none)

### HIGH

**FND-201 — API-Key `jti` wird nicht gespeichert**
- Datei: `backend/api/db/crud/users.py:201`
- Beschreibung: `create_key` setzt `jti = None`, obwohl das generierte Token einen `jti` enthält. Der DB-Eintrag verknüpft Token und Eintrag nicht.
- Impact: Widerruf über `TokenBlacklist.jti` funktioniert für API-Keys nicht.
- Empfehlung: `jti` aus dem generierten Token extrahieren und in `APIKEY.jti` speichern.

**FND-204 — API-Key-Widerruf löscht nur DB-Eintrag, nicht das laufende Token**
- Datei: `backend/api/db/crud/users.py:170-186`
- Beschreibung: `blacklist_api_key` führt `db.delete(key)` aus, trägt aber keinen `TokenBlacklist`-Eintrag für den `jti` ein.
- Impact: Gelöschte API-Keys bleiben bis zu 10 Jahre gültig, solange Token nicht abgelaufen ist.
- Empfehlung: Bei Widerruf `jti` (nach FND-201 verfügbar) in `TokenBlacklist` eintragen.

### MEDIUM

**FND-101 — WebSocket exec führt kein Audit-Logging durch**
- Datei: `backend/api/routers/containers.py:255-460`
- Beschreibung: Interaktive Shell-Zugriffe werden nicht im Audit-Log erfasst.
- Impact: Kritische Mutation (Shell-Zugriff) bleibt unauditiert.
- Empfehlung: Nach erfolgreichem AuthZ-Check Audit-Log-Eintrag (Actor, container_id, shell) hinzufügen; keine Terminalinhalte loggen.

**FND-205 — API-Keys haben keinen eingeschränkten Scope**
- Datei: `backend/api/db/crud/users.py:201`, `backend/api/routers/users.py:322-334`
- Beschreibung: API-Keys erhalten denselben JWT-Claim wie Login-Token und haben volle Benutzerrechte.
- Impact: Kompromittierter API-Key = voller Account-Zugriff.
- Empfehlung: Optionalen Scope einführen oder klar dokumentieren, dass API-Keys volle Rechte haben.

**FND-301 — Audit-Log-Einträge sind manipulierbar und nicht vollständig**
- Datei: `backend/api/utils/audit.py:1-22`
- Beschreibung: Audit-Log ist synchrones SQLAlchemy-Model in derselben DB wie Anwendungsdaten. Keine Integritätssicherung (Hash/Signatur/WORM). Nicht alle Mutations-Endpunkte loggen konsistent.
- Impact: Admin oder Datenbank-Zugriff kann Audit-Trail löschen/ändern.
- Empfehlung: Konsistentes Audit-Logging auf allen Mutations-Endpunkten; optional Immutability-Maßnahmen (z. B. append-only Tabelle, Zeitstempel + Hash-Kette).

**FND-401 — Deprecated GET-Aliase auf Mutations-Endpunkten noch erreichbar**
- Dateien:
  - `backend/api/routers/apps.py:145` — `/{app_name}/update` (deprecated=True)
  - `backend/api/routers/apps.py:193` — `/actions/{app_name}/{action}` (deprecated=True)
  - `backend/api/routers/users.py:347` — `/api/keys/{key_id}` (deprecated=True)
- Beschreibung: State-ändernde Aktionen (Update, Action, API-Key-Widerruf) sind weiterhin per GET aufrufbar, obwohl README besagt, dass sie entfernt werden.
- Impact: CSRF via `<img src=...>` / Link-Klick möglich, besonders bei SameSite=lax auf Top-Level-Navigation.
- Empfehlung: GET-Aliase entfernen oder zumindest auf POST-only umstellen. Frontend-Build prüfen, ob er die GET-Aliase noch nutzt.

**FND-501 — Keine Startup-Selbstprüfung für Betriebsmodus-Konfiguration**
- Datei: `backend/api/settings.py`, `backend/api/main.py`
- Beschreibung: Es gibt keinen zusammenhängenden "Modus"-Begriff. `ENVIRONMENT=development` (Default) schaltet `SECURE_COOKIES` auto-detect. `YACHT_BLOCK_PUBLIC_IP_LOGIN=true` (Default) blockiert öffentliche IPs. `YACHT_ALLOW_PRIVATE_NETWORK_HOSTS=false` (Default) erzwingt Host-Header-Pinning. Beim Wechsel in den öffentlichen Modus muss der Nutzer fünf+ Variablen korrekt setzen; inkonsistente Kombinationen werden nicht erkannt.
- Impact: Fehlkonfiguration beim Öffentlich-Gang fällt nicht auf; Schutzschichten entfallen stillschweigend.
- Empfehlung: Startup-Check, der widersprüchliche/unsichere Kombinationen erkennt und im Log + UI warnt oder Start verweigert.

### LOW

**FND-102 — Globale SSE-Stats ohne Permission-Gate**
- Dateien: `backend/api/routers/apps.py:151`, `backend/api/routers/apps.py:278`
- Beschreibung: `/api/apps/stats` und `/api/apps/{app_name}/stats` erfordern nur `auth_check`, aber kein `check_permission("perm_start")`.
- Impact: Authentifizierter Benutzer ohne Operator-Rechten kann globalen Ressourcenverbrauch abrufen (Info-Disclosure).
- Empfehlung: `check_permission("perm_start")` konsistent auf alle Stats-Streams anwenden.

**FND-104 — SSE-Stats-Streams ohne Rate-Limiting**
- Dateien: `backend/api/routers/apps.py:151`, `backend/api/routers/apps.py:278`
- Beschreibung: App-Stats-Streams haben kein `@limiter.limit(...)`.
- Impact: Unbegrenzte SSE-Verbindungen können Server-Ressourcen binden.
- Empfehlung: `@limiter.limit("60/minute")` wie in `containers.py:64` hinzufügen.

**FND-601 — Sync docker-SDK im async Request-Pfad**
- Dateien:
  - `backend/api/utils/docker_client.py`
  - `backend/api/actions/compose.py:137-139`, `368-369`, `408`
  - `backend/api/actions/apps.py:428-429`
  - `backend/api/utils/apps.py:399-400`
- Beschreibung: `get_sync_docker_client()` erzeugt blockierende `docker.DockerClient`-Aufrufe, die in `run_in_executor` verpackt werden. Es gibt aber weiterhin Mischverwendung mit `aiodocker` auf demselben Container-State.
- Impact: Potential für Thread-Pool-Erschöpfung, Race-Conditions zwischen sync/async Client, unterschiedliche Fehlerbehandlung.
- Empfehlung: Analyse, ob alle Pfade auf `aiodocker` migriert werden können; `get_sync_docker_client` nur noch für explizit blockierende Hintergrundaufgaben verwenden.

**FND-602 — Doppelte Verzeichnisse `.Jules` und `.jules`**
- Pfad: `/home/user/projects/YachtPlus/.Jules` und `.jules`
- Beschreibung: Zwei Verzeichnisse mit fast identischem Namen, unterschiedlichem Inhalt. Auf case-insensitiven Dateisystemen (macOS, Windows) kollidieren sie.
- Impact: Datenverlust/Überschreibung bei Checkout auf Windows/macOS; Build-Portabilität.
- Empfehlung: Inhalt zusammenführen oder eines der Verzeichnisse umbenennen; `.gitignore` ggf. anpassen.

### INFO

**FND-103 — Compose-Projektliste erfordert `perm_start`**
- Datei: `backend/api/routers/compose.py:54-66`
- Beschreibung: Read-Endpunkt für Projektliste ist mit dem niedrigsten Operator-Gate geschützt. Dokumentation spricht von "read-only account", aber es gibt keine `perm_read`-Berechtigung.
- Empfehlung: Dokumentation anpassen oder dedizierte `perm_read` einführen.

**FND-701 — Frontend-State-Duplikation: Pinia installiert, aber Vuex 4 aktiv**
- Dateien: `frontend/package.json`, `frontend/src/main.js:150-151`, `frontend/src/store/modules/`, `frontend/src/views/`, `frontend/src/components/`
- Beschreibung: `pinia` ist installiert und `createPinia()` in `main.js` aktiv, aber alle Komponenten nutzen weiterhin `vuex` (`mapState`, `mapActions`, `useStore`, `this.$store`). 7 Vuex-Module unter `src/store/modules/`.
- Impact: Zwei parallele Zustandsquellen; Inkonsistenzen möglich, besonders bei Auth-State.
- Empfehlung: Modulweise Migration zu Pinia, ein Store pro Aufgabe; Frontend-Tests nach jedem Modul grün halten.

**FND-702 — i18n fehlt; Backend-Fehlermeldungen sind fertige Sätze**
- Dateien: `frontend/src/main.js`, `backend/api/routers/*.py`
- Beschreibung: Keine Vue I18n; Backend liefert häufig fertige englische Fehlertexte statt lokalisierte Codes.
- Empfehlung: Vue I18n v11 + Vuetify-Adapter einführen; Backend liefert `error.code` zusätzlich zur `message` (API-Shape bleibt stabil).

## Anhänge

- Roher pip-audit-Bericht: `report/pip-audit.md`
- Roher npm-audit-Bericht: `report/npm-audit.log`
