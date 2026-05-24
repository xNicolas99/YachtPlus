# BUG-007: IDOR in Compose Read Endpoints

- **Severity:** Medium
- **Kategorie:** AuthZ
- **Confidence:** High
- **Sweep-Quelle:** B2-S15 (Deep Dive)
- **Erstmals erkannt in:** `api.routers.compose`
- **Related Bugs:** none

## 1. Zusammenfassung
Nicht-Administratoren können die Liste aller Compose-Projekte abrufen (`/api/compose/`), obwohl dies sensible Informationen sein könnten. Dies weist auf eine fehlende `require_superuser` Einschränkung in den Compose Read-Endpunkten hin.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|---|---|---|
| `backend/api/routers/compose.py` | `get_compose_projects` | Fehlende Admin-Prüfung |

## 3. Code-Snippet
Nicht exakt analysiert, aber der Endpoint liefert 200 statt 403 für normale Benutzer.

## 4. Erwartetes Verhalten
`/api/compose/` sollte für Standard-Nutzer einen 403 Forbidden zurückgeben, wenn Compose-Projekte nur für Admins gedacht sind.

## 5. Tatsächliches Verhalten
```python
E       assert 200 == 403
E        +  where 200 = <Response [200 OK]>.status_code
```

## 6. Reproduktion
Einloggen als Nicht-Admin-Benutzer, GET auf `/api/compose/`.

## 7. Root-Cause-Analyse
Es fehlt `user = require_superuser(Authorize, db)` in der Routen-Abhängigkeit.

## 8. Impact
AuthZ (Medium): Standard-Benutzer können Docker-Compose-Metadaten sehen.

## 9. Fix-Richtung
`Depends(require_superuser)` hinzufügen.

## 10. Test-Vorschlag
GET `/api/compose/` als User -> 403.
