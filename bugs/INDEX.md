# Bug Index

| ID | Severity | Kategorie | Titel | Datei | Confidence |
|---|---|---|---|---|---|
| BUG-003 | Critical | Injection | Command-Injection in Compose-Actions über unvalidierten `action`-Parameter | backend/api/actions/compose.py | High (reproduziert durch Code-Analyse) |
| BUG-004 | Low | Config | Fehlende `COMPOSE_DIR` Deklaration in Pydantic Settings | backend/api/settings.py | Medium |
| BUG-005 | Low | ErrorHandling | Bare `except:` blockiert sauberes Fehler-Logging beim Stats-Parsing | backend/api/actions/containers.py | High |
| BUG-001 | Low | Logging | Semgrep Log-Leak Warning (False Positive) | backend/api/routers/containers.py | High (statisch erkannt) |
| BUG-002 | Low | Other | Semgrep Hardcoded Password Warning (False Positive, Dummy-Hash) | backend/api/routers/users.py | High (statisch erkannt) |
