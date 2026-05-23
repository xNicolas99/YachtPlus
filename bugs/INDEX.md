# Bug Index

| ID | Severity | Kategorie | Titel | Datei | Confidence |
|---|---|---|---|---|---|
| BUG-001 | High | Injection | Potential Container Exec Command Injection via WebSocket Shell Parameter | backend/api/routers/containers.py | High |
| BUG-005 | High | Other | SSRF Protection Fail-Open on DNS Resolution Error | backend/api/db/crud/templates.py | High |
| BUG-002 | Medium | Auth | JWT Refresh does not validate user status (active/exists) | backend/api/routers/users.py | High |
| BUG-006 | Medium | Auth | IP Spoofing / Rate Limit Evasion via X-Real-IP / X-Forwarded-For | backend/api/utils/security.py | High |
| BUG-003 | Medium | Other | API Key deletion uses HTTP GET method instead of DELETE | backend/api/routers/users.py | High |
| BUG-004 | Medium | Config | Missing Rate Limiting on API Key creation | backend/api/routers/users.py | Medium |
