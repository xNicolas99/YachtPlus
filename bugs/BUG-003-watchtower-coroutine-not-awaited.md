# BUG-003: Unawaited coroutine in watchtower service triggers compose actions silently

- **Severity:** High
- **Kategorie:** Concurrency / BusinessLogic
- **Confidence:** High
- **Sweep-Quelle:** B2-S6 (Mechanical Sweep)
- **Erstmals erkannt in:** `backend/api/services/watchtower.py:30`
- **Related Bugs:** none

## 1. Zusammenfassung
Der Watchtower-Service ruft in der Funktion `process_webhook` die asynchrone Funktion `compose_action(project_name, "pull")` und `compose_action(project_name, "up")` auf, verwendet dabei aber kein `await`. Das führt zu einem `RuntimeWarning: coroutine 'compose_action' was never awaited` und bedeutet, dass die Container-Updates nie tatsächlich ausgeführt werden.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|---|---|---|
| `backend/api/services/watchtower.py` | 30, 34 | Aufruf von `compose_action` ohne `await` |

## 3. Code-Snippet
```python
# backend/api/services/watchtower.py
def process_webhook(payload: dict, db: Session):
    # ...
    if project_name:
        # These are async functions being called from a sync (or async?) context without await
        compose_action(project_name, "pull")
        # ...
        compose_action(project_name, "up")
```

## 4. Erwartetes Verhalten
Wenn Watchtower einen Webhook sendet, dass ein Image aktualisiert wurde, soll YachtPlus via Docker Compose den neuen Container pullen und starten.

## 5. Tatsächliches Verhalten
```python
RuntimeWarning: coroutine 'compose_action' was never awaited
```
Die Compose-Aktion wird als Coroutine-Objekt erstellt und direkt verworfen, ohne jemals in der Event-Loop eingeplant zu werden. Das Update findet nicht statt.

## 6. Reproduktion
Einen POST-Request mit leerem Body (oder validem Watchtower Payload) an `/api/watchtower/` senden:
```bash
curl -i -X POST http://localhost:8000/api/watchtower/
```

## 7. Root-Cause-Analyse
Die Funktion `compose_action` aus `api.actions.compose` ist eine asynchrone Funktion (`async def compose_action(...)`), wird aber im Watchtower-Webhook-Handler scheinbar synchron aufgerufen (fehlendes `await`). Da FastAPI Endpoints synchron sein dürfen, muss hier entweder die Route/Funktion `async` gemacht und `await` verwendet werden, oder die Coroutine muss per `asyncio.run_coroutine_threadsafe` bzw. `asyncio.create_task` eingeplant werden.

## 8. Impact
BusinessLogic: Die Watchtower-Integration für automatische Compose-Updates (YachtPlus als Proxy) ist komplett funktionslos (High).

## 9. Fix-Richtung
`await` vor die Aufrufe von `compose_action` setzen und sicherstellen, dass die Handler-Funktion (`process_webhook` bzw. der API-Endpunkt) `async def` ist.

## 10. Test-Vorschlag
Ein POST Request auf `/api/watchtower/` mit gültigem Payload darf keine "coroutine was never awaited" Warnungen erzeugen und muss den Compose-Prozess triggern (kann durch Mocking von `compose_action` verifiziert werden).

## 11. Referenzen
Python `asyncio` Docs.
