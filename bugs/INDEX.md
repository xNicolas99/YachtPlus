# Bug Hunt Index

| ID | Severity | Kategorie | Titel | Datei | Confidence |
|----|----------|-----------|-------|-------|------------|
| 001 | Critical | Injection | Beliebige Codeausführung via Container-Start | api/actions/apps.py | High |
| 002 | Medium | Auth | Hardcoded Bcrypt Hash (Dummy Hash) | api/routers/users.py | High |
| 003 | Medium | ErrorHandling | Bare except in WebSocket-Handler verbirgt Fehler | api/routers/containers.py | High |
| 004 | Medium | Config | Potenzielles Binden an alle Interfaces (0.0.0.0) | api/actions/apps.py | Medium |
| 005 | Low | Other | Mehrdeutiger Variablenname "l" | api/utils/apps.py | High |
| 006 | Low | ErrorHandling | Bare except beim Abrufen von Registries | api/utils/registries.py | High |
| 007 | Low | Other | Ungenauer Type-Check mit type() == ... | api/utils/templates.py | High |
| 008 | Low | ErrorHandling | Bare except beim Parsen von CPUs in Templates | api/utils/apps.py | High |
