| ID  | Severity | Kategorie | Sweep | Titel | Datei:Zeile | Confidence |
|-----|----------|-----------|-------|-------|-------------|------------|
| 001 | High | AuthZ | 2 | Missing Auth Decorator on get_users | backend/api/routers/users.py:37 | High |
| 002 | High | AuthZ | 2 | Missing Role Check in delete_user | backend/api/routers/users.py:55 | High |
| 003 | Medium | ErrorHandling | 6 | Generic Catch-All in login | backend/api/routers/users.py:185 | High |
| 004 | High | AuthZ | 2 | Missing Auth in read_template_variables | backend/api/routers/app_settings.py:28 | High |
| 005 | Medium | Validation | 3 | Missing CSRF in set_template_variables | backend/api/routers/app_settings.py:40 | Medium |
| 006 | High | Validation | 3 | Unsafe Upload in import_settings | backend/api/routers/app_settings.py:65 | High |
| 007 | Medium | ErrorHandling | 6 | Masked Error in start_container | backend/api/routers/containers.py:140 | High |
| 008 | Low | ErrorHandling | 6 | 500 on missing ID in delete_container | backend/api/routers/containers.py:204 | High |
| 009 | Medium | Logging | 6 | Stack Trace in WS Exec | backend/api/routers/containers.py:245 | High |
| 010 | Medium | Performance | 5 | Missing limit in search | backend/api/routers/search.py:26 | High |
| 011 | High | AuthZ | 2 | Auth Bypass in search | backend/api/routers/search.py:26 | High |
| 012 | Low | Validation | 3 | Missing Rate Limit in search | backend/api/routers/search.py:26 | Medium |
| 013 | Medium | Injection | 2 | Unsafe file write path | backend/api/routers/setup/setup.py:53 | Medium |
| 014 | Medium | Auth | 2 | Missing Rate Limit on Setup | backend/api/routers/setup/setup.py:101 | High |
| 015 | Medium | ErrorHandling | 6 | Masked Exception in file write | backend/api/routers/setup/setup.py:55 | High |
