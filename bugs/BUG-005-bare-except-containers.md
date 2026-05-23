# BUG-005-bare-except-containers

**Severity:** Low
**Kategorie:** ErrorHandling
**Confidence:** High
**Erstmals erkannt in:** `backend/api/actions/containers.py`
**Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)

In `api/actions/containers.py` (Zeilen ~248, 257) wird ein generisches `except:` ohne Spezifizierung eines Exception-Typs und mit einem simplen `pass` verwendet. Das fängt potenziell alle Fehler ab, inklusive `SystemExit` und `KeyboardInterrupt`, und erschwert das Debugging immens.

## 2. Betroffene Stellen

| Datei                            | Zeile(n) | Rolle                |
| -------------------------------- | -------- | -------------------- |
| backend/api/actions/containers.py| 248      | Error Handling       |
| backend/api/actions/containers.py| 257      | Error Handling       |

## 3. Code-Snippet (eingebettet)

```python
                try:
                    mem_stats = stats.get("memory_stats", {})
                    mem_current = mem_stats.get("usage", 0)
                    mem_limit = mem_stats.get("limit", 0)
                    if mem_limit > 0:
                        mem_percent = (mem_current / mem_limit) * 100.0
                except:
                    pass
```

## 4. Erwartetes Verhalten

Fehlerbehandlung sollte spezifisch sein, z.B. `except Exception as e:` (oder besser `KeyError`, `ValueError`), und der Fehler sollte nach Möglichkeit geloggt werden. Auf gar keinen Fall darf ein nacktes `except:` verwendet werden.

## 5. Tatsächliches Verhalten

Das `except:` blockiert alle Exceptions ungesehen, wodurch Fehler beim Parsen von Docker-Stats stillschweigend verschluckt werden.

## 6. Reproduktion

Starten von Containern mit beschädigten oder abweichenden `memory_stats` und aufrufen des Container Stats Endpoints.

## 7. Root-Cause-Analyse

`bare except` Konstrukte in Python verletzen PEP-8 und best practices, da sie auch Signale wie Strg+C verschlucken können.

## 8. Impact

* User-Impact: Debugging wird extrem erschwert, falls Stats nicht korrekt angezeigt werden.
* Daten-Impact: Keiner.
* Security-Impact: Keiner.
* Performance-Impact: Keiner.

## 9. Fix-Richtung (kein Code, nur Strategie)

Ersetze `except:` durch `except Exception as e:` und füge idealerweise ein Logging hinzu oder logge zumindest im Debug-Modus. Alternativ fange spezifisch `(KeyError, ValueError, TypeError)` ab.

## 10. Test-Vorschlag

Regressionstest, bei dem ein mock container mit falschen (z.B. fehlenden/korrupten) Stats angefragt wird. Teste ob `cpu_percent` und `memory_percent` Default-Werte annehmen und kein interner Absturz auftritt, während der Backend-Linter/Flake8 diesen Bereich fehlerfrei (ohne E722 bare except) durchläuft.

## 11. Referenzen

* `backend/api/actions/containers.py`

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: In `api/actions/containers.py` werden bare `except:` Blöcke verwendet, um Fehler beim Parsen von Docker-Stats zu fangen.

Aktueller Code:

```python
                try:
                    mem_stats = stats.get("memory_stats", {})
                    mem_current = mem_stats.get("usage", 0)
                    mem_limit = mem_stats.get("limit", 0)
                    if mem_limit > 0:
                        mem_percent = (mem_current / mem_limit) * 100.0
                except:
                    pass
```

Bitte:

1. Ändere die `except:` in `except Exception as e:`. Füge, wenn angemessen, ein kurzes `logger.debug` oder `logger.warning` hinzu, statt nur `pass`.
2. Führe diese Änderung in allen betroffenen try/except-Blöcken im Stats-Parsing-Code durch.
3. Überprüfe, dass `flake8` hier nicht mehr meckert (E722 do not use bare 'except').
