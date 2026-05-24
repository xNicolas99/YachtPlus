# Audit Walkthrough

api/actions/apps.py
LOC: 689
Funktionen: get_running_apps, check_app_update, normalize_ports, get_apps, get_app, get_app_processes, get_app_logs, check_container_conflicts, deploy_app, Merge, launch_app, _launch_app_sync, AiodockerCompatWrapper, app_action, app_update, _read_self_id, _get_self_id, _update_self, update_self_in_background, check_self_update, generate_support_bundle, log_generator, _stat_generator, stat_generator, all_stat_generator, process_app_stats
Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
Datei-spezifische Risiko-Checks (mind. 3):
    - get_app_processes (Zeile 201): nutzt aiodocker stats_generator ohne Timeouts, Risiko bei Docker-Daemon Latenz.
    - deploy_app (Zeile 281): ruft `write_compose` mit unsanitized form.env payload auf, mögliche Traversal/Injection in Compose File via ENV Keys. -> BUG-101
    - check_container_conflicts (Zeile 230): iteriert über alle container und prüft Port-Kollision, O(N^2) verhalten wenn viele Container existieren (Performance Bottleneck).
Findings in dieser Datei: BUG-101
0-Findings-Begründung: N/A

api/actions/compose.py
LOC: 373
Funktionen: run_in_thread, _run_compose_command, _compose_action_sync, compose_action, check_dockerhost, _compose_app_action_sync, compose_app_action, _get_compose_projects_sync, get_compose_projects, _get_compose_sync, get_compose, _write_compose_sync, write_compose, _delete_compose_sync, delete_compose, _generate_support_bundle_sync, generate_support_bundle
Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
Datei-spezifische Risiko-Checks (mind. 3):
    - _run_compose_command (Zeile 42): subprocess.run hat arg-injection mitigations weil shell=False genutzt wird und args in liste getrennt sind.
    - write_compose (Zeile 120): Keine file size limits auf uploaded compose.yml, Risiko durch DoS bei extrem großen YAML Files. -> BUG-102
    - run_in_thread (Zeile 30): fehlende Exception-Catching Logic in Worker Threads, kann zu Silent Failures im Background führen.
Findings in dieser Datei: BUG-102
0-Findings-Begründung: N/A

api/actions/containers.py
LOC: 298
Funktionen: get_containers, stream_stats_generator, get_logs_generator, get_stats, get_all_stats
Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
Datei-spezifische Risiko-Checks (mind. 3):
    - stream_stats_generator (Zeile 45): aiodocker async stats call ohne close auf Stream Error, Memory/Socket Leak wenn Client die WS Verbindung kappt. -> BUG-103
    - get_containers (Zeile 14): Iteriert über alle Container des Docker Hosts ohne Limit/Offset.
    - get_logs_generator (Zeile 110): Keine Timestamp-Sanitization beim Parsen der Docker Daemon Logs (könnte Format-Drift sein).
Findings in dieser Datei: BUG-103
0-Findings-Begründung: N/A

api/actions/dashboard.py
LOC: 217
Funktionen: get_dashboard_stats
Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
Datei-spezifische Risiko-Checks (mind. 3):
    - get_dashboard_stats (Zeile 11): Vulture meldet unused function, aber API Router importiert sie implizit (False Positive).
    - get_dashboard_stats : Holt alle templates und containers synchronisiert im Dashboard, N+1 Query Charakteristik da apps einzeln iteriert werden.
    - Error Handling: Sammelt Fehler aus `get_running_apps` und gibt sie ungefiltert an Client weiter.
Findings in dieser Datei: keine
0-Findings-Begründung: Erwartetes Problem wäre ein N+1 Performance-Bottleneck, jedoch werden die Daten durch Pydantic Models serialisiert und die Anzahl an Templates in einer Yacht Instanz ist historisch gering (<100), wodurch das Risiko akzeptiert wird.

api/routers/users.py
LOC: 406
Funktionen: get_users, get_user_by_id, update_user, delete_user, change_role
Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
Datei-spezifische Risiko-Checks (mind. 3):
    - _TIMING_DUMMY_BCRYPT_HASH (Zeile 34): Semgrep warnt generic.secrets.security.detected-bcrypt-hash (False Positive da dummy wert, aber wird geloggt) -> BUG-005
    - get_users (Zeile 45): Offset/Limit Pagination ohne stabile ORDER BY (nur created_at DESC)
    - delete_user (Zeile 178): Soft-Delete Flag, aber Cascade-Logic fehlt auf session-token.
Findings in dieser Datei: BUG-005
0-Findings-Begründung: N/A

api/routers/containers.py
LOC: 442
Funktionen: exec_websocket, get_container_info
Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
Datei-spezifische Risiko-Checks (mind. 3):
    - Exception Handler in exec_websocket (Zeile 279): Loggt setup_pending token in error log -> BUG-007
    - exec_websocket: Auth Check über query parameters anstelle von Headers (Design-Schwäche bei WS, aber mitigiert durch Short-Lived Tokens).
    - get_container_info: IDs werden vor Docker-Daemon Request über fastapi Path-Validator `constr` gesichert (verhindert Command Injection).
Findings in dieser Datei: BUG-007
0-Findings-Begründung: N/A

api/utils/security.py
LOC: 197
Funktionen: get_ip, check_ip_restriction, record_login_attempt
Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
Datei-spezifische Risiko-Checks (mind. 3):
    - get_ip (Zeile 16): Binding to all interfaces Bandit Warnung B104 -> BUG-010
    - check_ip_restriction (Zeile 40): X-Forwarded-For Header wird ausgelesen, aber Spoofing-Schutz erfordert vorgelagerten Proxy (Dokumentiertes Verhalten in Yacht).
    - record_login_attempt (Zeile 60): Lockout mechanismus speichert State im SQLite, parallel Logins könnten DB-Locks auslösen (SQLite Write Concurrency).
Findings in dieser Datei: BUG-010
0-Findings-Begründung: N/A

api/routers/setup/setup.py
LOC: 278
Funktionen: file_upload, setup_admin, validate_config
Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
Datei-spezifische Risiko-Checks (mind. 3):
    - file_upload (Zeile 40): Insecure usage of temp directory Bandit B108 -> BUG-013
    - setup_admin (Zeile 120): Endpoint prüft `setup_pending` Lock, Race-Condition bei gleichzeitigem POST möglich, falls Transaktion nicht Strict ist.
    - validate_config (Zeile 200): SSRF-Schutz auf Template URLs vorhanden durch `validators.url()`.
Findings in dieser Datei: BUG-013
0-Findings-Begründung: N/A
