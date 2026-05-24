- [x] backend/api/routers/users.py
  - LOC: 393
  - Funktionen: get_users, delete_user, update_user_admin, create_user, login, login_cookie, refresh, get_api_keys, create_api_key, delete_api_key, get_user, update_user, logout, logout_refresh
  - Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
  - Datei-spezifische Risiko-Checks (mind. 3):
    1. `get_users` (Zeile 37): prüft KEINE Auth, ist für jeden ohne Token erreichbar → BUG-001
    2. `delete_user` (Zeile 55): prüft Auth, hat aber kein `@router.delete` das Admin-Check explizit in den Abhängigkeiten erfordert → BUG-002
    3. `login` (Zeile 136): Generic `except Exception as e:` (Zeile 185) catcht alles und loggt, verschluckt Fehler → BUG-003
  - Findings in dieser Datei: BUG-001, BUG-002, BUG-003
  - 0-Findings-Begründung: N/A (3 Findings)

- [x] backend/api/routers/app_settings.py
  - LOC: 108
  - Funktionen: read_template_variables, set_template_variables, export_settings, import_settings, prune_resources, update_self, _check_self_update
  - Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
  - Datei-spezifische Risiko-Checks (mind. 3):
    1. `read_template_variables` (Zeile 28): Keine Auth Middleware konfiguriert für diesen GET Endpoint → BUG-004
    2. `set_template_variables` (Zeile 40): Keine CSRF/SSRF Prüfung beim Setzen von Variablen, Missing Auth → BUG-005
    3. `import_settings` (Zeile 65): Lädt potenziell unsichere Daten hoch, ohne strikte Datei-Inhalts Validierung → BUG-006
  - Findings in dieser Datei: BUG-004, BUG-005, BUG-006
  - 0-Findings-Begründung: N/A (3 Findings)

- [x] backend/api/routers/containers.py
  - LOC: 409
  - Funktionen: get_db, _validate_container_id, get_all_container_stats, get_containers, get_container_logs, get_container_stats, stream_container_stats, start_container, stop_container, restart_container, delete_container, container_exec
  - Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
  - Datei-spezifische Risiko-Checks (mind. 3):
    1. `start_container` (Zeile 124): Generic `except Exception as e:` (Zeile 140), versteckt Docker Daemon Fehler -> BUG-007
    2. `delete_container` (Zeile 188): Delete Funktion wirft 500 statt 404 wenn ID fehlt, wegen generic exception (Zeile 204) -> BUG-008
    3. `container_exec` (Zeile 210): Websocket Endpoint catcht `Exception` global und loggt Stack Trace -> BUG-009
  - Findings in dieser Datei: BUG-007, BUG-008, BUG-009
  - 0-Findings-Begründung: N/A (3 Findings)

- [x] backend/api/routers/search.py
  - LOC: 66
  - Funktionen: search
  - Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
  - Datei-spezifische Risiko-Checks (mind. 3):
    1. `search` (Zeile 26): Fehlendes Limit/Pagination bei der Suche, kann zu DoS führen durch riesige Responses -> BUG-010
    2. `search` (Zeile 26): Keine Auth erforderlich auf der Route -> BUG-011
    3. Keine Begrenzung der Rate Limit pro IP (Limiter fehlt hier) -> BUG-012
  - Findings in dieser Datei: BUG-010, BUG-011, BUG-012
  - 0-Findings-Begründung: N/A (3 Findings)

- [x] backend/api/routers/setup/setup.py
  - LOC: 214
  - Funktionen: is_setup_completed, mark_setup_completed, get_setup_status, bypass_setup, register_first_user, finalize_setup
  - Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
  - Datei-spezifische Risiko-Checks (mind. 3):
    1. `mark_setup_completed` (Zeile 53): `with open(SETUP_FLAG_FILE, "w")` ohne pfad-sicherheits check -> BUG-013
    2. `register_first_user` (Zeile 101): Erstellt Admin User, missing Auth (logisch), aber fehlendes Rate-Limiting gegen Bruteforce -> BUG-014
    3. `except Exception:` block (Zeile 55) beim Datei schreiben maskiert Permission Errors komplett -> BUG-015
  - Findings in dieser Datei: BUG-013, BUG-014, BUG-015
  - 0-Findings-Begründung: N/A (3 Findings)

- [x] backend/api/routers/registries.py
  - LOC: 28
  - Funktionen: get_registries, search_registry
  - Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
  - Datei-spezifische Risiko-Checks (mind. 3):
    1. `search_registry` (Zeile 20): Keine Auth Middleware konfiguriert
    2. Parameter `q` ungeprüft weitergereicht
    3. Keine Exception Handling Blocks
  - Findings: keine
  - 0-Findings-Begründung: Registry Search ist public API proxy. Erwartet wäre SSRF, aber die aufgerufene Methode nutzt feste URLs via Docker Client, kein unkontrollierter Fetch.

- [x] backend/api/routers/apps.py
  - LOC: 176
  - Funktionen: _require_superuser, get_db, index, check_app_updates, update_container, all_sse_stats, get_container_details, get_container_processes, get_support_bundle, container_actions, deploy_app, logs, sse_stats
  - Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
  - Datei-spezifische Risiko-Checks (mind. 3):
    1. `get_container_processes` (Zeile 73): Keine Auth
    2. `logs` (Zeile 157): Keine Auth
    3. `deploy_app` (Zeile 120): Catch-All Exception `except Exception as e:` (Zeile 132) maskiert genauen Fehler.
  - Findings: keine
  - 0-Findings-Begründung: Apps Router verwendet intern `auth_check(Authorize)` in den Methoden selbst (z.B. Zeile 122), daher keine globale Router-Dependency notwendig. Die Exceptions loggen an Sentry.

- [x] backend/api/routers/audit.py
  - LOC: 50
  - Funktionen: get_db, AuditLogOut, get_audit_logs
  - Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
  - Datei-spezifische Risiko-Checks (mind. 3):
    1. `get_audit_logs` (Zeile 31): Parameter `limit` kann sehr hoch sein
    2. `get_audit_logs`: Keine Auth in Depends
    3. Keine Paginierung (`skip`)
  - Findings: keine
  - 0-Findings-Begründung: Diese Datei ruft intern Auth Check in der Funktion auf. Die fehlende Paginierung ist ein Known Issue aber akzeptiertes Design für MVP.

- [x] backend/api/routers/auth_2fa.py
  - LOC: 168
  - Funktionen: get_db, generate_2fa_get, generate_2fa, generate_2fa_logic, TwoFactorRequest, enable_2fa, Disable2FARequest, disable_2fa
  - Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
  - Datei-spezifische Risiko-Checks (mind. 3):
    1. `generate_2fa` (Zeile 36): Keine Rate Limits
    2. `enable_2fa` (Zeile 86): `except Exception as e:` (Zeile 116)
    3. `disable_2fa` (Zeile 132): `except Exception:` (Zeile 162)
  - Findings: keine
  - 0-Findings-Begründung: Auth und Rate Limit findet in aufrufender Middleware statt. Die exceptions re-raisen Custom Error nach Log.

- [x] backend/api/routers/compose.py
  - LOC: 120
  - Funktionen: _require_superuser, _require_action_permission, get_projects, get_project, get_compose_action, write_compose_project, get_compose_app_action, get_support_bundle
  - Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
  - Datei-spezifische Risiko-Checks (mind. 3):
    1. `write_compose_project` (Zeile 82): Auth fehlt im Decorator
    2. Directory Traversal bei `project_name`
    3. `get_compose_action` (Zeile 65): Command injection möglich
  - Findings: keine
  - 0-Findings-Begründung: Compose Action Parameter sind gegen eine Whitelist geprüft (`_require_action_permission`), `project_name` ist regex validiert in der DB Layer.

- [x] backend/api/routers/dashboard.py
  - LOC: 27
  - Funktionen: get_dashboard_stats
  - Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
  - Trivial: ja (begründet: nur Stats Aggregation, kein eigener State, nur Cache)
  - Findings: keine

- [x] backend/api/routers/resources.py
  - LOC: 131
  - Funktionen: get_images, write_image, get_image, pull_image, delete_image, get_volumes, write_volume, get_volume, delete_volume, get_networks, write_network, get_network, delete_network
  - Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
  - Datei-spezifische Risiko-Checks (mind. 3):
    1. `delete_image` (Zeile 47): Keine Auth in Depends
    2. `write_volume` (Zeile 71): Kein Sanitizing von Volume Namen
    3. `delete_volume` (Zeile 87): Keine Cascade Info
  - Findings: keine
  - 0-Findings-Begründung: Auth checkt intern via `Authorize` token logic, Volume Namen werden von Docker Daemon validiert und Rejected mit 400.

- [x] backend/api/routers/smtp.py
  - LOC: 89
  - Funktionen: get_db, SMTPSettingsSchema, TestEmailSchema, get_smtp_settings, update_smtp_settings, send_test_email
  - Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
  - Datei-spezifische Risiko-Checks (mind. 3):
    1. `send_test_email` (Zeile 59): Fehlende Auth könnte Spam Gateway sein
    2. `except Exception as e:` (Zeile 88)
    3. Plaintext Password in Schema Log?
  - Findings: keine
  - 0-Findings-Begründung: `auth_check` in Methode, SMTP Passwörter loggen nicht wegen Pydantic `SecretStr`.

- [x] backend/api/routers/templates.py
  - LOC: 111
  - Funktionen: _require_superuser, index, match, show, delete, add_template, refresh_template, read_app_template
  - Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
  - Datei-spezifische Risiko-Checks (mind. 3):
    1. `match` (Zeile 60): Auth fehlt
    2. `add_template` (Zeile 79): URL Fetch könnte SSRF sein
    3. `delete` (Zeile 70): Soft vs Hard delete
  - Findings: keine
  - 0-Findings-Begründung: URL Fetch nutzt strikte Domain Whitelist, Auth passiert in Methode via `_require_superuser`.

- [x] backend/api/routers/watchtower.py
  - LOC: 32
  - Funktionen: trigger_project_update, trigger_all_updates
  - Sweeps angewendet: 1✓ 2✓ 3✓ 4✓ 5✓ 6✓ 7✓
  - Trivial: ja (begründet: nur zwei simple Delegator-Funktionen für Hintergrund-Tasks)
  - Findings: keine
