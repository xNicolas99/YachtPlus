# BUG-011: Auth Bypass in search

- **Severity:** High
- **Kategorie:** AuthZ
- **Confidence:** High
- **Sweep-Quelle:** 2
- **Erstmals erkannt in:** backend/api/routers/search.py:26
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
The search endpoint queries multiple internal tables (including templates/containers) but lacks an authentication requirement.

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
```

## 4. Erwartetes Verhalten
Search should be restricted to authenticated users to prevent data leakage.

## 5. Tatsächliches Verhalten
An unauthenticated user can enumerate container names or internal templates.

## 6. Reproduktion
Statischer Code Analysis Befund (Sweep 2).

## 7. Root-Cause-Analyse
Missing `Authorize: get_auth_wrapper = Depends(get_auth_wrapper)` parameter.

## 8. Impact
- User: Bekommt unerwartetes Verhalten oder Daten Leak
- Security: Schwäche in API Boundary
- Performance: Möglicher Ressourcenverbrauch

## 9. Fix-Richtung (Strategie, kein Code)
Add the authorization dependency and call `auth_check(Authorize)`.

## 10. Test-Vorschlag
Perform a search request without a token and assert a 401 response.

## 11. Referenzen
FastAPI Error Handling Docs, OWASP Top 10.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)
> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht erkunden, frag bei Bedarf nach.
>
> **Bug:** Auth Bypass in search
> **Datei(en):** backend/api/routers/search.py
> **Aktuelles Verhalten:** An unauthenticated user can enumerate container names or internal templates.
> **Erwartetes Verhalten:** Search should be restricted to authenticated users to prevent data leakage.
> **Root Cause:** Missing `Authorize: get_auth_wrapper = Depends(get_auth_wrapper)` parameter.
> **Vorgeschlagene Fix-Richtung:** Add the authorization dependency and call `auth_check(Authorize)`.
> **Testfall der danach passen muss:** Perform a search request without a token and assert a 401 response.
>
> Aktueller Code:
> ```python
> @router.get("/")
async def search(
    q: str = Query(..., min_length=1, max_length=SEARCH_QUERY_MAX_LEN),
    db: Session = Depends(get_db)
):
> ```
>
> Bitte:
> 1. Minimalen Fix implementieren.
> 2. Regressionstest aus Punkt 10 schreiben.
> 3. Begründen warum dein Fix den Root Cause behebt, nicht nur das Symptom.
> 4. Risiken/Seiteneffekte für mein Review auflisten.
