# Bug Hunt Index

ID | Severity | Kategorie | Sweep | Titel | Datei:Zeile | Confidence
---|---|---|---|---|---|---
005 | Suspicion | Auth | 2 | Semgrep meldet einen hardcoded bcrypt hash im Code. Dieser w... | backend/api/routers/users.py:34 | Low
007 | Medium | Logging | 2 | Der WebSocket-Endpoint für Container exec loggt einen `setup... | backend/api/routers/containers.py:279 | High
010 | Low | Config | 1 | Bandit (B104) warnt vor `Possible binding to all interfaces.... | backend/api/utils/security.py:16 | High
013 | Low | Config | 1 | Bandit (B108) warnt vor `Probable insecure usage of temp fil... | backend/api/routers/setup/setup.py:40 | Medium
101 | Medium | Validation | 3 | In `deploy_app` wird das von User gesendete DeployForm nahez... | backend/api/actions/apps.py:281 | Medium
102 | Low | ResourceLeak | 3 | Der Upload-Endpoint für Compose-Dateien `write_compose` prüf... | backend/api/actions/compose.py:120 | High
103 | Medium | ResourceLeak | 4 | `stream_stats_generator` öffnet einen asynchronen Stream zum... | backend/api/actions/containers.py:45 | High
