# BUG-010: Missing limit in search

- **Severity:** Medium
- **Kategorie:** Performance
- **Confidence:** High
- **Sweep-Quelle:** 5
- **Erstmals erkannt in:** backend/api/routers/search.py:26
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
The global search endpoint does not enforce a hard limit on the number of returned results, potentially causing severe memory spikes on the server.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/search.py | 26 | router endpoint |

## 3. Code-Snippet
```python
@router.get("/")
async def search(
    q: str = Query(..., min_length=1, max_length=SEARCH_QUERY_MAX_LEN),
    db: Session = Depends(get_db)
):
    results = crud.search_all(db, q)
```

## 4. Erwartetes Verhalten
The endpoint should implement pagination (limit/offset) or enforce a maximum result cap (e.g., 50 items).

## 5. Tatsächliches Verhalten
The database query fetches and serializes all matching rows.

## 6. Reproduktion
Statischer Code Analysis Befund (Sweep 5).

## 7. Root-Cause-Analyse
Missing limit clause in the underlying ORM call or missing parameter on the API layer.

## 8. Impact
- User: Bekommt unerwartetes Verhalten oder Daten Leak
- Security: Schwäche in API Boundary
- Performance: Möglicher Ressourcenverbrauch

## 9. Fix-Richtung (Strategie, kein Code)
Add a `limit=50` parameter and enforce it during the query.

## 10. Test-Vorschlag
Create 200 matching records, query the search endpoint, and verify only <=50 are returned.

## 11. Referenzen
FastAPI Error Handling Docs, OWASP Top 10.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)
> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht erkunden, frag bei Bedarf nach.
>
> **Bug:** Missing limit in search
> **Datei(en):** backend/api/routers/search.py
> **Aktuelles Verhalten:** The database query fetches and serializes all matching rows.
> **Erwartetes Verhalten:** The endpoint should implement pagination (limit/offset) or enforce a maximum result cap (e.g., 50 items).
> **Root Cause:** Missing limit clause in the underlying ORM call or missing parameter on the API layer.
> **Vorgeschlagene Fix-Richtung:** Add a `limit=50` parameter and enforce it during the query.
> **Testfall der danach passen muss:** Create 200 matching records, query the search endpoint, and verify only <=50 are returned.
>
> Aktueller Code:
> ```python
> @router.get("/")
async def search(
    q: str = Query(..., min_length=1, max_length=SEARCH_QUERY_MAX_LEN),
    db: Session = Depends(get_db)
):
    results = crud.search_all(db, q)
> ```
>
> Bitte:
> 1. Minimalen Fix implementieren.
> 2. Regressionstest aus Punkt 10 schreiben.
> 3. Begründen warum dein Fix den Root Cause behebt, nicht nur das Symptom.
> 4. Risiken/Seiteneffekte für mein Review auflisten.
