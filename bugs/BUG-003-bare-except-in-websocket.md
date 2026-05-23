# BUG-003: Bare except in WebSocket-Handler verbirgt Fehler

- **Severity:** Medium
- **Kategorie:** ErrorHandling
- **Confidence:** High (statisch erkannt durch ruff, E722)
- **Erstmals erkannt in:** api/routers/containers.py:273
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
Im WebSocket-Handler für die Container-Terminals (`api/routers/containers.py`) werden Ausnahmen mittels `except:` (ohne Typ) stillschweigend geschluckt (`pass`). Dies maskiert potenziell kritische Fehler (z.B. Memory Errors, Thread-Abbrüche, KeyboardInterrupts) und macht das Debugging von Terminal-Verbindungsabbrüchen unmöglich, da die Fehler weder protokolliert noch korrekt behandelt werden.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/containers.py | 273, 307 | Bare except Blöcke im WebSocket Task |

## 3. Code-Snippet (eingebettet)
```python
// backend/api/routers/containers.py:271
                                await exec_instance.resize(w=cmd["cols"], h=cmd["rows"])
                                continue
                        except:
                            pass
```

## 4. Erwartetes Verhalten
Ausnahmen sollten spezifisch gefangen werden (z. B. `except WebSocketDisconnect:` oder `except DockerError:`). Wenn eine allgemeine Ausnahme gefangen werden muss, sollte `except Exception as e:` verwendet und der Fehler zumindest protokolliert (`logger.error()`) werden.

## 5. Tatsächliches Verhalten
Jegliche Fehler (einschließlich Syntaxfehlern im Try-Block oder SystemExits) werden durch das bare `except:` ignoriert. Der Code fährt einfach fort oder stirbt still.

## 6. Reproduktion
Statisch nachgewiesen durch Ruff (Fehlercode E722).
Wenn das Resize des Terminals aus irgendeinem Grund fehlschlägt (z.B. Container existiert nicht mehr), schlägt die Methode fehl, aber es wird nicht geloggt und der Administrator kann nicht nachvollziehen, warum das Terminal nicht mehr auf Resize reagiert.

## 7. Root-Cause-Analyse
Bequemlichkeit oder mangelnde Kenntnis der spezifischen Exceptions beim Prototyping. Ein leeres `except:` fängt auch interne System-Exceptions ab, was ein Anti-Pattern in Python ist.

## 8. Impact
- **User-Impact:** Terminal verhält sich möglicherweise instabil (Resize geht nicht) ohne Fehlermeldung.
- **Daten-Impact:** Keiner.
- **Security-Impact:** Keiner, aber erschwert das Logging von potenziellen Angriffen auf die WebSocket-Schnittstelle.

## 9. Fix-Richtung (kein Code, nur Strategie)
Ersetze das bare `except:` durch `except Exception as e:` und logge die Exception mit `logger.warning("Resize failed: %s", e)`.

## 10. Test-Vorschlag
Mocke `exec_instance.resize` in einem WebSocket-Test so, dass es eine `Exception` wirft, und überprüfe, ob der Fehler im Log landet und die WebSocket-Verbindung nicht sofort abbricht.

## 11. Referenzen
- Verwandte Funktionen/Module im Repo: `backend/api/routers/containers.py`

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.
>
> **Bug:** Bare except in WebSocket-Handler verbirgt Fehler
> **Datei(en):** backend/api/routers/containers.py
> **Aktuelles Verhalten:** Bare `except:` Blöcke (Zeile 273 und 307) ignorieren Fehler komplett (`pass`).
> **Erwartetes Verhalten:** Fehler sollen spezifisch oder zumindest als `Exception` gefangen und protokolliert werden.
> **Root Cause:** Anti-Pattern `except:` schluckt alle System- und Laufzeitfehler.
> **Vorgeschlagene Fix-Richtung:** Ändere `except:` zu `except Exception as e:` und füge ein `logger.warning/error` hinzu.
> **Testfall der danach passen muss:** Nicht zwingend für die Logik, aber ein UnitTest auf das WebSocket-Resize mit Fehlschlag sollte existieren.
>
> Aktueller Code:
> ```python
>                         except:
>                             pass
> ```
>
> Bitte:
> 1. Implementiere den Fix mit minimaler Änderung.
> 2. Schreibe den Regressionstest aus §10.
> 3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
> 4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
