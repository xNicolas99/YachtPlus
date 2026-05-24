# BUG-008: TypeError in write_image when image_name is missing/null

- **Severity:** Medium
- **Kategorie:** Validation / ErrorHandling
- **Confidence:** High
- **Sweep-Quelle:** B2-S14 / B2-S15 (Deep Dive)
- **Erstmals erkannt in:** `api.actions.resources.write_image`
- **Related Bugs:** none

## 1. Zusammenfassung
Wenn `/api/resources/images/` aufgerufen wird (POST) und der Pydantic-Body ein `image` Feld hat, aber nicht als String (bzw. None), dann stürzt die Methode `write_image` in `api.actions.resources` mit einem `TypeError: argument of type 'NoneType' is not iterable` ab, weil sie `delim in image_tag` ausführt, ohne auf `None` zu prüfen.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|---|---|---|
| `backend/api/actions/resources.py` | 59 | String-Operation auf möglichem None-Wert |

## 3. Code-Snippet
```python
    async def write_image(image_tag):
        delim = ":"
        repo, tag = None, image_tag
        if delim in image_tag:  # <--- HIER knallts wenn image_tag None ist
```

## 4. Erwartetes Verhalten
Die Pydantic-Validierung sollte `None` abfangen, oder die Funktion sollte graceful fehlschlagen (400 Bad Request).

## 5. Tatsächliches Verhalten
```python
E       TypeError: argument of type 'NoneType' is not iterable
```

## 6. Reproduktion
```bash
curl -X POST -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d '{"image_name": "nginx"}' http://localhost:8000/api/resources/images/
```
(Das Schema erwartet ein Feld `image`, was hier weggelassen oder als None geliefert wurde in meinem Test).

## 7. Root-Cause-Analyse
Der Test sendet `{"image_name": "nginx"}`, aber das geforderte Pydantic Schema verlangt ein Feld `image: str`. Da Pydantic vermutlich `image: str = None` hat oder der Wert sonstwie durchschlüpft, knallt es in der Action-Logik.

## 8. Impact
Führt zu 500 statt 422 oder 400 (Low-Medium).

## 9. Fix-Richtung
Validierung im Pydantic Schema verschärfen oder if-check in `write_image`.

## 10. Test-Vorschlag
Sende POST an `/api/resources/images/` ohne `image`-Key. Muss 422 ergeben.
