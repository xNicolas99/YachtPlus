# BUG-009: Stack Trace in WS Exec

- **Severity:** Medium
- **Kategorie:** Logging
- **Confidence:** High
- **Sweep-Quelle:** 6
- **Erstmals erkannt in:** backend/api/routers/containers.py:245
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
A global exception handler in the websocket execution endpoint can inadvertently leak stack traces or internal state to the websocket client.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/containers.py | 245 | router endpoint |

## 3. Code-Snippet
```python
    except Exception as e:
        await websocket.send_text(f"Internal Error: {str(e)}")
```

## 4. Erwartetes Verhalten
Internal errors should be logged server-side and generic messages sent to the client.

## 5. Tatsächliches Verhalten
Raw exception strings are transmitted over the websocket.

## 6. Reproduktion
Statischer Code Analysis Befund (Sweep 6).

## 7. Root-Cause-Analyse
Directly stringifying `e` to the client instead of using a sanitized error message.

## 8. Impact
- User: Bekommt unerwartetes Verhalten oder Daten Leak
- Security: Schwäche in API Boundary
- Performance: Möglicher Ressourcenverbrauch

## 9. Fix-Richtung (Strategie, kein Code)
Log `e` internally and send a generic string like 'Connection failed' to the client.

## 10. Test-Vorschlag
Trigger an internal failure in the WS setup and assert the client receives a generic error.

## 11. Referenzen
FastAPI Error Handling Docs, OWASP Top 10.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)
> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht erkunden, frag bei Bedarf nach.
>
> **Bug:** Stack Trace in WS Exec
> **Datei(en):** backend/api/routers/containers.py
> **Aktuelles Verhalten:** Raw exception strings are transmitted over the websocket.
> **Erwartetes Verhalten:** Internal errors should be logged server-side and generic messages sent to the client.
> **Root Cause:** Directly stringifying `e` to the client instead of using a sanitized error message.
> **Vorgeschlagene Fix-Richtung:** Log `e` internally and send a generic string like 'Connection failed' to the client.
> **Testfall der danach passen muss:** Trigger an internal failure in the WS setup and assert the client receives a generic error.
>
> Aktueller Code:
> ```python
>     except Exception as e:
        await websocket.send_text(f"Internal Error: {str(e)}")
> ```
>
> Bitte:
> 1. Minimalen Fix implementieren.
> 2. Regressionstest aus Punkt 10 schreiben.
> 3. Begründen warum dein Fix den Root Cause behebt, nicht nur das Symptom.
> 4. Risiken/Seiteneffekte für mein Review auflisten.
