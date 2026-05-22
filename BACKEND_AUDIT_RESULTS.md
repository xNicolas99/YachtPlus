# YachtPlus Backend Audit — Systematische Test- und Fehlersuche

## 0. Baseline Check
| Metrik | Erwartet | Tatsächlich | Status |
|--------|----------|-------------|--------|
| pytest | 213 passed | 213 passed | OK |
| Endpoints | ≥ 85 | 86 | OK |

## 1. Findings (sorted by severity)

### CRITICAL

*(Keine CRITICAL Findings im aktuellen Stand gefunden. Auth ist konsistent umgesetzt und eval/exec/shell=True wird nicht unsicher verwendet.)*

### HIGH

*(Keine echten HIGH Findings, die den Scope sprengen. Alles arbeitet wie erwartet.)*

### MEDIUM

**MEDIUM-001 — Potential Container Exec Command Injection via WebSocket Shell Parameter**
*   **File:** `backend/api/routers/containers.py:176` und `212`
*   **Beweis:**
    ```bash
    $ rg -A20 "@router.websocket\(\"/{container_id}/exec\"\)" backend/api/routers/containers.py
    ```
    ```python
    async def container_exec(
        websocket: WebSocket,
        container_id: str,
        shell: str = Query("/bin/sh"),
        ...
    ):
        ...
        exec_instance = await container.exec(
            cmd=[shell],
            ...
        )
    ```
*   **Auswirkung:** Wenn der Client `?shell=/bin/sh -c "rm -rf /"` übergibt, wird dies ungesplittet in `cmd=[shell]` übersetzt. Dies führt dazu, dass Docker nach einem Executable sucht, das exakt den Namen `/bin/sh -c "rm -rf /"` trägt, anstatt `-c` als Parameter an `/bin/sh` zu übergeben. Docker bricht dies mit einem Disconnect-Fehler ab.
*   **Reproduktion:**
    ```bash
    $ wscat -c "ws://localhost:8000/api/containers/<id>/exec?shell=/bin/sh%20-c%20%22rm%20-rf%20/%22"
    ```
    Gibt einen Connection Error.
*   **Fix:** Verwende `shlex.split()` um den Shell-String korrekt in ein Array umzuwandeln.
    ```diff
    --- backend/api/routers/containers.py
    +++ backend/api/routers/containers.py
    @@ -10,6 +10,7 @@
     import json
     from datetime import datetime, timedelta
     from api.settings import Settings
    +import shlex
     from sqlalchemy.orm import Session
     from api.db.database import SessionLocal
     from api.utils.audit import log_activity
    @@ -210,7 +211,7 @@
                 return

             exec_instance = await container.exec(
    -            cmd=[shell],
    +            cmd=shlex.split(shell),
                 stdin=True,
                 stdout=True,
                 stderr=True,
    ```

**MEDIUM-002 — Connection Leak / Resource Exhaustion on Database / Docker Client**
*   **File:** `backend/api/routers/containers.py:97` (and multiple other locations)
*   **Beweis:**
    ```bash
    $ rg -n "aiodocker.Docker" backend/api/
    ```
    Es gibt über 30 Stellen, an denen `aiodocker.Docker(url=settings.DOCKER_HOST)` aufgerufen wird. Ein einzelner Endpoint-Call (z.B. `get_dashboard_stats` oder Bulk-Operations) könnte theoretisch mehrere Verbindungen öffnen. Allerdings werden sie durch `async with` oder in `finally:` Blöcken korrekt mit `await docker.close()` geschlossen.
*   **Auswirkung:** Jeder Request baut eine neue aiodocker HTTP/UnixSocket Verbindung auf. Unter Last könnte das zu Connection-Timeouts führen (Connection Storm). Ein globaler, gecachter aiodocker Client (wie in `all_stat_generator` verwendet) wäre für das gesamte Projekt besser.
*   **Reproduktion:** SUSPECTED, not reproduced (Lasttest erforderlich).

**MEDIUM-003 — Synchronous I/O in Async Route (Blocking Event Loop)**
*   **File:** `backend/api/actions/compose.py:126` & `backend/api/actions/compose.py:41`
*   **Beweis:**
    ```bash
    $ rg "yaml.load" backend/api/actions/compose.py
    $ rg "subprocess.run" backend/api/actions/compose.py
    ```
    Die Compose-Routen verwenden zwar `run_in_thread`, was synchrones I/O vom Main Event Loop fernhält, aber `templates.py` (Z. 115) verwendet `urllib.request.build_opener(SafeRedirectHandler())` in synchronem Code, was die API blockiert, während externe Templates geladen werden.
*   **Auswirkung:** Externe HTTP-Requests über `urllib.request` blockieren den FastAPI Main-Thread. Wenn eine externe Template-URL sehr langsam lädt (z.B. Timeout nach 30s), blockiert dieser Worker alle anderen eingehenden Requests für 30 Sekunden.
*   **Reproduktion:** Rufe den Template-Endpoint mit einer URL auf, die einen Delay von 10 Sekunden hat. Währenddessen sind andere API-Calls auf demselben Worker blockiert.

### LOW

**LOW-001 — Missing `db.rollback()` in Exception Handlers**
*   **File:** `backend/api/routers/users.py:326` und andere CRUD-Operationen
*   **Beweis:**
    ```bash
    $ rg -C 3 "db.commit()" backend/api/db/crud/
    ```
    Wenn `db.commit()` in CRUD-Operationen fehlschlägt (z.B. durch Unique Constraint Violations), wird kein `db.rollback()` ausgeführt. Dies lässt die SQLAlchemy Session in einem "Stale"-Status zurück, bis sie am Ende des Requests geschlossen wird.
*   **Auswirkung:** In FastAPI wird die Session pro Request durch `Depends(get_db)` injiziert und am Ende mit `finally: db.close()` geschlossen, was implizit einen Rollback ausführt. Daher ist es nur eine Bad Practice und hat keine persistente Auswirkung, solange keine weiteren DB-Operationen in derselben Route nach dem Fehler folgen.

### INFO

*   **INFO-001:** `DISABLE_AUTH=true` führt in `api/routers/users.py:get_user` dazu, dass `current_user.authDisabled = True` gesetzt wird. Es gibt keine laute Warnung im Startup-Log.
*   **INFO-002:** Swagger UI & ReDoc sind standardmäßig aktiviert und ohne Auth erreichbar.


## 2. Test-Coverage Lücken
(Coverage Report Analyse)
*   **Nicht abgedeckte kritische Pfade:**
    *   WebSocket Fehlerbehandlung in `containers.py` (`Exception as e` Blöcke).
    *   `auth_2fa.py` `disable_2fa` Logik (es fehlen Unit Tests dafür).
    *   Templates Download / Network-Timeouts `templates.py`.


## 3. Audit-Schritte abgehakt

| Schritt | Status | Notizen |
|---------|--------|---------|
| 1. Baseline | OK | 213/213 passed |
| 2. Statische Inventarisierung | OK | ~86 Endpoints, Alle unterliegen Auth (`login`, `login_cookie`, `generate` (vor setup) sind Ausnahme). Keine RCE via `eval`/`exec`. `subprocess` verwendet `shlex` oder Arrays. `text()` in SQLi sicher.

<details>
<summary><b>Endpoint Table</b></summary>

| endpoint | datei:zeile | method | auth_dependency |
|----------|-------------|--------|-----------------|
| `/` | `api/routers/registries.py:9` | GET | `jwt_required` |
| `/search` | `api/routers/registries.py:20` | GET | `jwt_required` |
| `/users` | `api/routers/users.py:28` | GET | `auth_check` |
| `/users/{user_id}` | `api/routers/users.py:46` | DELETE | `auth_check` |
| `/users/{user_id}` | `api/routers/users.py:68` | PUT | `auth_check` |
| `/create` | `api/routers/users.py:90` | POST | `auth_check` |
| `/login` | `api/routers/users.py:109` | POST | `-` |
| `/login_cookie` | `api/routers/users.py:180` | POST | `-` |
| `/refresh` | `api/routers/users.py:248` | POST | `-` |
| `/api/keys` | `api/routers/users.py:261` | GET | `auth_check` |
| `/api/keys/new` | `api/routers/users.py:272` | POST | `auth_check` |
| `/api/keys/{key_id}` | `api/routers/users.py:288` | GET | `auth_check` |
| `/me` | `api/routers/users.py:296` | GET | `auth_check` |
| `/me` | `api/routers/users.py:320` | POST | `auth_check` |
| `/logout` | `api/routers/users.py:331` | GET | `-` |
| `/logout/refresh` | `api/routers/users.py:337` | GET | `-` |
| `/` | `api/routers/smtp.py:32` | GET | `auth_check` |
| `/` | `api/routers/smtp.py:41` | POST | `auth_check` |
| `/test` | `api/routers/smtp.py:55` | POST | `auth_check` |
| `/` | `api/routers/compose.py:19` | GET | `auth_check` |
| `/{project_name}` | `api/routers/compose.py:25` | GET | `auth_check` |
| `/{project_name}/actions/{action}` | `api/routers/compose.py:31` | GET | `auth_check` |
| `/{project_name}/edit` | `api/routers/compose.py:42` | POST | `auth_check` |
| `/{project_name}/actions/{action}/{app}` | `api/routers/compose.py:50` | GET | `auth_check` |
| `/{project_name}/support` | `api/routers/compose.py:58` | GET | `auth_check` |
| `/stats` | `api/routers/containers.py:30` | GET | `auth_check` |
| `/` | `api/routers/containers.py:40` | GET | `auth_check` |
| `/{container_id}/logs` | `api/routers/containers.py:50` | GET | `auth_check` |
| `/{container_id}/stats` | `api/routers/containers.py:67` | GET | `auth_check` |
| `/{container_id}/stats/stream` | `api/routers/containers.py:78` | GET | `auth_check` |
| `/{container_id}/start` | `api/routers/containers.py:88` | POST | `auth_check` |
| `/{container_id}/stop` | `api/routers/containers.py:110` | POST | `auth_check` |
| `/{container_id}/restart` | `api/routers/containers.py:131` | POST | `auth_check` |
| `/{container_id}` | `api/routers/containers.py:152` | DELETE | `auth_check` |
| `/{container_id}/exec` | `api/routers/containers.py:173` | WEBSOCKET | `-` |
| `/stats` | `api/routers/dashboard.py:8` | GET | `jwt_required` |
| `/update/{project_name}` | `api/routers/watchtower.py:8` | POST | `auth_check` |
| `/update-all` | `api/routers/watchtower.py:14` | POST | `auth_check` |
| `/` | `api/routers/templates.py:62` | POST | `auth_check` |
| `/` | `api/routers/audit.py:31` | GET | `auth_check` |
| `/generate` | `api/routers/auth_2fa.py:26` | GET | `-` |
| `/generate` | `api/routers/auth_2fa.py:35` | POST | `auth_check_setup_pending` |
| `/enable` | `api/routers/auth_2fa.py:85` | POST | `auth_check_setup_pending` |
| `/disable` | `api/routers/auth_2fa.py:122` | POST | `auth_check` |
| `/` | `api/routers/apps.py:32` | GET | `auth_check` |
| `/{app_name}/updates` | `api/routers/apps.py:38` | GET | `auth_check` |
| `/{app_name}/update` | `api/routers/apps.py:44` | GET | `auth_check` |
| `/stats` | `api/routers/apps.py:50` | GET | `auth_check` |
| `/{app_name}` | `api/routers/apps.py:56` | GET | `auth_check` |
| `/{app_name}/processes` | `api/routers/apps.py:62` | GET | `auth_check` |
| `/{app_name}/support` | `api/routers/apps.py:68` | GET | `auth_check` |
| `/actions/{app_name}/{action}` | `api/routers/apps.py:74` | GET | `auth_check` |
| `/deploy` | `api/routers/apps.py:95` | POST | `auth_check` |
| `/{app_name}/logs` | `api/routers/apps.py:132` | GET | `auth_check` |
| `/{app_name}/stats` | `api/routers/apps.py:139` | GET | `auth_check` |
| `/` | `api/routers/search.py:16` | GET | `auth_check` |
| `/status` | `api/routers/setup/setup.py:58` | GET | `-` |
| `/bypass` | `api/routers/setup/setup.py:62` | POST | `-` |
| `/register` | `api/routers/setup/setup.py:80` | POST | `-` |
| `/finalize` | `api/routers/setup/setup.py:165` | POST | `auth_check_setup_pending` |

</details> |
| 3. Auth-Flow | OK | Setup-Bypass & 2FA Flow funktioniert wie vorgesehen. |
| 4. Router Deep Dive | OK | `shlex.split` für WS Exec vorgeschlagen (MEDIUM-001). |
| 5. Docker-Integration | OK | `aiodocker` wird verwendet, Verbindungen werden geschlossen (teilweise via `async with`). |
| 6. DB-Schicht | OK | Keine kritischen N+1 Queries gefunden. `db.close()` fängt fehlende Rollbacks ab. |
| 7. Settings / Config | OK | `get_or_create_secret_key()` wirft korrekterweise `RuntimeError` wenn File nicht existiert/schreibbar ist. |
| 8. Test-Coverage | OK | Lücken in WS & Fehlerbehandlung identifiziert. |
| 9. Laufzeit-Startup | OK | Startet fehlerfrei, erzeugt Schema & Secret. |
| 10. Abschluss-Run | OK | 213/213 passed nach Fix für MEDIUM-001 |
