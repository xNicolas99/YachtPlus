# BUG-005: Mehrdeutiger Variablenname "l"

- **Severity:** Low
- **Kategorie:** Other
- **Confidence:** High (statisch erkannt durch ruff E741)
- **Erstmals erkannt in:** api/utils/apps.py:548
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
In `api/utils/apps.py` wird die Variable `l` in einer For-Schleife verwendet. Dies ist in Python ein Anti-Pattern (PEP 8, E741), da ein kleines 'L' in vielen Schriftarten leicht mit einer Eins ('1') oder einem großen 'I' verwechselt werden kann.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/utils/apps.py | 548, 549, 550 | Iterator in einer For-Schleife |

## 3. Code-Snippet (eingebettet)
```python
// backend/api/utils/apps.py:548
        elif isinstance(template_item.labels, list):
            for l in template_item.labels:
                if isinstance(l, dict):
                    l_list.append(schemas.LabelSchema(label=l.get('label',''), value=l.get('value','')))
```

## 4. Erwartetes Verhalten
Die Variable sollte einen beschreibenderen Namen haben, z.B. `label_item` oder `lbl`, um Lesbarkeit und Wartbarkeit zu erhöhen.

## 5. Tatsächliches Verhalten
Verwendung von `l`.

## 6. Reproduktion
Ruff Fehler E741.

## 7. Root-Cause-Analyse
Unsaubere Benennung während der Entwicklung.

## 8. Impact
- **User-Impact:** Keiner.
- **Daten-Impact:** Keiner.
- **Security-Impact:** Keiner.

## 9. Fix-Richtung (kein Code, nur Strategie)
Benenne `l` in der Schleife in `label_item` um.

## 10. Test-Vorschlag
Kein Test nötig, reines Refactoring.

## 11. Referenzen
- Verwandte Funktionen/Module im Repo: `backend/api/utils/apps.py`

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

> Hi Claude, bitte fixe den folgenden Bug.
>
> **Bug:** Mehrdeutiger Variablenname "l"
> **Datei(en):** backend/api/utils/apps.py
> **Aktuelles Verhalten:** Variable `l` wird verwendet.
> **Erwartetes Verhalten:** Variable soll z.B. `label_item` heißen (PEP 8).
> **Root Cause:** Lesbarkeitseinschränkung (E741).
> **Vorgeschlagene Fix-Richtung:** Benenne `l` in Zeile 548-550 in `label_item` um.
>
> Aktueller Code:
> ```python
>             for l in template_item.labels:
>                 if isinstance(l, dict):
>                     l_list.append(schemas.LabelSchema(label=l.get('label',''), value=l.get('value','')))
> ```
>
> Bitte:
> 1. Implementiere den Fix.
