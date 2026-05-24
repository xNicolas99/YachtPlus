# BUG-006: 500 Internal Server Error in /api/apps/deploy

- **Severity:** High
- **Kategorie:** BusinessLogic
- **Confidence:** High
- **Sweep-Quelle:** B2-S15 (Deep Dive)
- **Erstmals erkannt in:** `api.routers.apps.deploy_app`
- **Related Bugs:** none

## 1. Zusammenfassung
Wenn ein valider Payload an `/api/apps/deploy` (z.B. `{"name": "test-app", "image": "nginx:latest"}`) gesendet wird, schlägt der Server mit einem HTTP 500 Fehler fehl.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|---|---|---|
| `backend/api/routers/apps.py` | `deploy_app` | Endpunkt schlägt fehl |

## 3. Code-Snippet
Unbekannt, da der Callstack im Test-Output abgeschnitten war.

## 4. Erwartetes Verhalten
Der Request sollte bei erfolgreicher Validierung entweder den Deployment-Prozess starten und 200/201/202 zurückgeben oder 400 (Bad Request), falls bestimmte Parameter fehlen, aber nicht crashen.

## 5. Tatsächliches Verhalten
```python
E       assert 500 == 200
E        +  where 500 = <Response [500 Internal Server Error]>.status_code
```

## 6. Reproduktion
```bash
curl -X POST -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d '{"name": "test-app", "image": "nginx:latest"}' http://localhost:8000/api/apps/deploy
```

## 7. Root-Cause-Analyse
Eventuell ein Aufruf im Docker SDK, der `await` vergessen hat oder Parameter erwartet, die nicht im Mock oder im Live-System gemockt sind.

## 8. Impact
Deployment von Containern via UI ist kaputt.

## 9. Fix-Richtung
Fehlersuche im `/api/apps/deploy` Router durchführen (Logs ansehen) und den fehlschlagenden API-Call patchen.

## 10. Test-Vorschlag
`/api/apps/deploy` sollte keinen 500 werfen.
