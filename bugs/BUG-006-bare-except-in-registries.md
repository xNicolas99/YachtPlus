# BUG-006: Bare except beim Abrufen von Registries

- **Severity:** Low
- **Kategorie:** ErrorHandling
- **Confidence:** High (statisch erkannt durch ruff E722)
- **Erstmals erkannt in:** api/utils/registries.py:151
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
Beim Verarbeiten von Docker-Registry-Informationen in `api/utils/registries.py` (Zeile 151) wird ein bare `except:` verwendet, um Fehler beim Parsen der JSON-Antwort (oder beim Request selbst) abzufangen. Dies schluckt alle Exceptions lautlos und gibt keine Hinweise in den Logs, falls externe Registries nicht erreichbar sind oder kaputte Daten liefern.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/utils/registries.py | 151 | Fehlerbehandlung für HTTP Requests/JSON parsing |

## 3. Code-Snippet (eingebettet)
```python
// backend/api/utils/registries.py:149
                    if resp.status_code == 200:
                        data = resp.json()
                except:
                    pass
```

## 4. Erwartetes Verhalten
Fehler beim Netzwerkaufruf oder JSON-Parsing sollten spezifisch gefangen werden (z.B. `httpx.RequestError`, `json.JSONDecodeError`) oder zumindest als `Exception` mit einem `logger.warning/error` protokolliert werden.

## 5. Tatsächliches Verhalten
Fehler werden lautlos ignoriert (`pass`).

## 6. Reproduktion
Statisch nachgewiesen durch ruff (E722). Wenn eine Registry kaputtes JSON liefert, stürzt die Funktion nicht ab, aber der Fehler ist schwer zu debuggen.

## 7. Root-Cause-Analyse
Bequeme, aber unsaubere Fehlerbehandlung.

## 8. Impact
- **User-Impact:** Keine direkten Abstürze, aber fehlende/unvollständige Registry-Daten ohne Erklärung.
- **Daten-Impact:** Keiner.
- **Security-Impact:** Keiner.

## 9. Fix-Richtung (kein Code, nur Strategie)
Ersetze das `except:` durch `except Exception as e:` und füge eine Log-Meldung hinzu (`logger.warning(f"Failed to process registry response: {e}")`).

## 10. Test-Vorschlag
Mocke den `resp.json()` Aufruf, damit er eine Exception wirft, und prüfe, ob die Exception geloggt wird.

## 11. Referenzen
- Verwandte Funktionen/Module im Repo: `backend/api/utils/registries.py`

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

> Hi Claude, bitte fixe den folgenden Bug.
>
> **Bug:** Bare except beim Abrufen von Registries
> **Datei(en):** backend/api/utils/registries.py
> **Aktuelles Verhalten:** Bare `except:` ignoriert Fehler lautlos.
> **Erwartetes Verhalten:** Exception soll spezifisch gefangen und geloggt werden.
> **Root Cause:** E722 Anti-Pattern.
> **Vorgeschlagene Fix-Richtung:** Ändere zu `except Exception as e:` und füge `logger.warning` hinzu.
>
> Aktueller Code:
> ```python
>                 except:
>                     pass
> ```
>
> Bitte:
> 1. Implementiere den Fix.
