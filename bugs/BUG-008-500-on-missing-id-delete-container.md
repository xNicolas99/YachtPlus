# BUG-008: 500 on missing ID in delete_container

- **Severity:** Low
- **Kategorie:** ErrorHandling
- **Confidence:** High
- **Sweep-Quelle:** 6
- **Erstmals erkannt in:** backend/api/routers/containers.py:204
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
If a non-existent container ID is passed, the deletion logic throws a generic Exception which is caught as a 500 rather than a 404.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/containers.py | 204 | router endpoint |

## 3. Code-Snippet
```python
    try:
        await remove_docker_container(container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

## 4. Erwartetes Verhalten
Missing resources should result in an HTTP 404.

## 5. Tatsächliches Verhalten
Missing container results in an HTTP 500 Server Error.

## 6. Reproduktion
Statischer Code Analysis Befund (Sweep 6).

## 7. Root-Cause-Analyse
Not distinguishing between a 'Not Found' error from Docker and a genuine execution failure.

## 8. Impact
- User: Bekommt unerwartetes Verhalten oder Daten Leak
- Security: Schwäche in API Boundary
- Performance: Möglicher Ressourcenverbrauch

## 9. Fix-Richtung (Strategie, kein Code)
Catch a 404 from the Docker daemon and raise `HTTPException(404)`.

## 10. Test-Vorschlag
Call DELETE with a fake ID and assert response status is 404.

## 11. Referenzen
FastAPI Error Handling Docs, OWASP Top 10.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)
> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht erkunden, frag bei Bedarf nach.
>
> **Bug:** 500 on missing ID in delete_container
> **Datei(en):** backend/api/routers/containers.py
> **Aktuelles Verhalten:** Missing container results in an HTTP 500 Server Error.
> **Erwartetes Verhalten:** Missing resources should result in an HTTP 404.
> **Root Cause:** Not distinguishing between a 'Not Found' error from Docker and a genuine execution failure.
> **Vorgeschlagene Fix-Richtung:** Catch a 404 from the Docker daemon and raise `HTTPException(404)`.
> **Testfall der danach passen muss:** Call DELETE with a fake ID and assert response status is 404.
>
> Aktueller Code:
> ```python
>     try:
        await remove_docker_container(container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
> ```
>
> Bitte:
> 1. Minimalen Fix implementieren.
> 2. Regressionstest aus Punkt 10 schreiben.
> 3. Begründen warum dein Fix den Root Cause behebt, nicht nur das Symptom.
> 4. Risiken/Seiteneffekte für mein Review auflisten.
