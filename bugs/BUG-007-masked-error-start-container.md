# BUG-007: Masked Error in start_container

- **Severity:** Medium
- **Kategorie:** ErrorHandling
- **Confidence:** High
- **Sweep-Quelle:** 6
- **Erstmals erkannt in:** backend/api/routers/containers.py:140
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
The `start_container` endpoint suppresses underlying Docker engine errors by catching `Exception` generically and returning a generic 500 error.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/containers.py | 140 | router endpoint |

## 3. Code-Snippet
```python
    try:
        await start_docker_container(container_id)
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to start container")
```

## 4. Erwartetes Verhalten
Docker engine exceptions (e.g., port conflicts) should be relayed with appropriate 400-level HTTP codes and messages.

## 5. Tatsächliches Verhalten
All errors result in a 500, making it impossible for the user to understand what went wrong.

## 6. Reproduktion
Statischer Code Analysis Befund (Sweep 6).

## 7. Root-Cause-Analyse
Use of generic catch-all rather than handling `aiodocker.exceptions.DockerError`.

## 8. Impact
- User: Bekommt unerwartetes Verhalten oder Daten Leak
- Security: Schwäche in API Boundary
- Performance: Möglicher Ressourcenverbrauch

## 9. Fix-Richtung (Strategie, kein Code)
Catch `DockerError` and return its status code/message.

## 10. Test-Vorschlag
Mock a Docker conflict error and assert the API returns a 409 status.

## 11. Referenzen
FastAPI Error Handling Docs, OWASP Top 10.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)
> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht erkunden, frag bei Bedarf nach.
>
> **Bug:** Masked Error in start_container
> **Datei(en):** backend/api/routers/containers.py
> **Aktuelles Verhalten:** All errors result in a 500, making it impossible for the user to understand what went wrong.
> **Erwartetes Verhalten:** Docker engine exceptions (e.g., port conflicts) should be relayed with appropriate 400-level HTTP codes and messages.
> **Root Cause:** Use of generic catch-all rather than handling `aiodocker.exceptions.DockerError`.
> **Vorgeschlagene Fix-Richtung:** Catch `DockerError` and return its status code/message.
> **Testfall der danach passen muss:** Mock a Docker conflict error and assert the API returns a 409 status.
>
> Aktueller Code:
> ```python
>     try:
        await start_docker_container(container_id)
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to start container")
> ```
>
> Bitte:
> 1. Minimalen Fix implementieren.
> 2. Regressionstest aus Punkt 10 schreiben.
> 3. Begründen warum dein Fix den Root Cause behebt, nicht nur das Symptom.
> 4. Risiken/Seiteneffekte für mein Review auflisten.
