| ID | Severity | Kategorie | Titel | Datei | Confidence |
|----|----------|-----------|-------|-------|------------|
| 002 | High | Injection | Command Injection in WebSocket exec (shlex.split mit user-controlled shell string) | backend/api/routers/containers.py | High |
| 003 | High | AuthZ | Fehlende Berechtigungsprüfung für Compose-Aktionen | backend/api/routers/compose.py | High |
| 007 | High | Business | Löschen des eigenen Admin-Users (oder des letzten Admins) nicht verhindert | backend/api/routers/users.py | High |
| 001 | High | Injection | Unsichere Deserialisierung mit yaml.load ohne SafeLoader Fallback | backend/api/actions/compose.py | High |
| 005 | Medium | ErrorHandling | Fehlendes db.rollback() bei Fehler in create_user | backend/api/db/crud/users.py | High |
| 004 | Medium | DB | Auskommentierter commit() beim Löschen von Templates in actions/compose.py | backend/api/db/crud/templates.py | High |
| 006 | Suspicion| Config | CORS Erlaubt Credentials mit potenziell wildcards/ungesicherten Origins | backend/api/settings.py | Low |
