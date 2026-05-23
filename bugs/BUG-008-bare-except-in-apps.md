# BUG-008: Bare except beim Parsen von CPUs in Templates

- **Severity:** Low
- **Kategorie:** ErrorHandling
- **Confidence:** High (statisch erkannt durch ruff E722)
- **Erstmals erkannt in:** api/utils/apps.py:467
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
In `api/utils/apps.py` (Zeile 467) wird versucht, die CPU-Konfiguration aus einem Template in einen Float-Wert zu konvertieren (`float(template_item.cpus)`). Schlägt dies fehl (z.B. weil der Wert leer oder ein ungültiger String ist), wird die Ausnahme durch ein bare `except:` lautlos ignoriert und der Wert einfach nicht gesetzt oder auf einem vorherigen Wert belassen.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/utils/apps.py | 467 | Fehlerbehandlung für Float-Parsing |

## 3. Code-Snippet (eingebettet)
```python
// backend/api/utils/apps.py:465
        try:
             form.cpus = float(template_item.cpus)
        except:
             pass
```

## 4. Erwartetes Verhalten
Ausnahmen wie `ValueError` oder `TypeError` (beim Konvertieren zu Float) sollten explizit gefangen werden. Im Fehlerfall sollte idealerweise ein Standardwert (z.B. `0.0`) zugewiesen werden oder eine Warnung protokolliert werden, damit ersichtlich ist, warum das Template-Feld ignoriert wurde.

## 5. Tatsächliches Verhalten
Jegliche Fehler werden durch `except:` ignoriert.

## 6. Reproduktion
Statisch nachgewiesen durch Ruff.

## 7. Root-Cause-Analyse
Bequemes Ignorieren von Parse-Fehlern.

## 8. Impact
- **User-Impact:** Falsche oder fehlende CPU-Limits in generierten Containern ohne Rückmeldung an den Nutzer.
- **Daten-Impact:** Keiner.
- **Security-Impact:** Keiner.

## 9. Fix-Richtung (kein Code, nur Strategie)
Ersetze das `except:` durch `except (ValueError, TypeError):` und setze eventuell einen sinnvollen Fallback (z.B. `form.cpus = 0.0` falls notwendig, abhängig von der Logik).

## 10. Test-Vorschlag
Kein zwingender Test, reines Error-Handling-Refactoring.

## 11. Referenzen
- Verwandte Funktionen/Module im Repo: `backend/api/utils/apps.py`

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

> Hi Claude, bitte fixe den folgenden Bug.
>
> **Bug:** Bare except beim Parsen von CPUs in Templates
> **Datei(en):** backend/api/utils/apps.py
> **Aktuelles Verhalten:** Bare `except:` ignoriert Parse-Fehler.
> **Erwartetes Verhalten:** Exception soll spezifisch gefangen werden.
> **Root Cause:** E722 Anti-Pattern.
> **Vorgeschlagene Fix-Richtung:** Ändere zu `except (ValueError, TypeError):` und prüfe ob ein Log oder Fallback-Wert sinnvoll ist.
>
> Aktueller Code:
> ```python
>         except:
>              pass
> ```
>
> Bitte:
> 1. Implementiere den Fix.
