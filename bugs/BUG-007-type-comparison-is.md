# BUG-007: Ungenauer Type-Check mit `type() == ...`

- **Severity:** Low
- **Kategorie:** Other
- **Confidence:** High (statisch erkannt durch ruff E721)
- **Erstmals erkannt in:** api/utils/templates.py:26
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
In `api/utils/templates.py` (Zeilen 26 und 48) wird die Typüberprüfung mittels `type(data[0]) == dict` durchgeführt. Dies ist in Python ein Anti-Pattern (Ruff E721), da es Subklassen nicht korrekt erkennt. Die empfohlene Methode ist `isinstance()`.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/utils/templates.py | 26, 48 | Typüberprüfung beim Parsen von Port-Listen |

## 3. Code-Snippet (eingebettet)
```python
// backend/api/utils/templates.py:26
def conv_ports2dict(data: List[str]) -> List[Dict[str, str]]:
    if len(data) > 0 and type(data[0]) == dict:
        delim = ":"
```

## 4. Erwartetes Verhalten
Typüberprüfungen sollten mit `isinstance(data[0], dict)` durchgeführt werden, um auch von `dict` erbende Klassen korrekt zu behandeln.

## 5. Tatsächliches Verhalten
Verwendung von `==` für den Typvergleich.

## 6. Reproduktion
Statisch nachgewiesen durch Ruff.

## 7. Root-Cause-Analyse
Unwissenheit über `isinstance` in Python.

## 8. Impact
- **User-Impact:** Vermutlich keiner in der aktuellen Implementierung, da meist primitive `dict`s und `list`s von JSON/Pydantic kommen.
- **Daten-Impact:** Keiner.
- **Security-Impact:** Keiner.

## 9. Fix-Richtung (kein Code, nur Strategie)
Ersetze `type(data[0]) == dict` durch `isinstance(data[0], dict)` und `type(data) == list` durch `isinstance(data, list)`.

## 10. Test-Vorschlag
Kein spezieller Test notwendig, reines Refactoring für Konformität mit PEP 8.

## 11. Referenzen
- Verwandte Funktionen/Module im Repo: `backend/api/utils/templates.py`

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

> Hi Claude, bitte fixe den folgenden Bug.
>
> **Bug:** Ungenauer Type-Check mit `type() == ...`
> **Datei(en):** backend/api/utils/templates.py
> **Aktuelles Verhalten:** `type(data[0]) == dict` wird verwendet.
> **Erwartetes Verhalten:** `isinstance(data[0], dict)` soll verwendet werden.
> **Root Cause:** E721 Anti-Pattern in Python.
> **Vorgeschlagene Fix-Richtung:** Ersetze die `type() ==` Vergleiche in den Zeilen 26 und 48 durch `isinstance()`.
>
> Aktueller Code:
> ```python
>     if len(data) > 0 and type(data[0]) == dict:
> ```
>
> Bitte:
> 1. Implementiere den Fix.
