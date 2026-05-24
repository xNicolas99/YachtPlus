# BUG-012: Missing Rate Limit in search

- **Severity:** Low
- **Kategorie:** Validation
- **Confidence:** Medium
- **Sweep-Quelle:** 3
- **Erstmals erkannt in:** backend/api/routers/search.py:26
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
The search endpoint performs intensive DB queries but is not protected by the global or local rate limiter, allowing scraping.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/search.py | 26 | router endpoint |

## 3. Code-Snippet
```python
@router.get("/")
async def search(
    q: str = Query(..., min_length=1)
):
```

## 4. Erwartetes Verhalten
Intensive read endpoints should be rate-limited (e.g., 20 requests per minute).

## 5. Tatsächliches Verhalten
No `@limiter.limit` decorator is applied.

## 6. Reproduktion
Statischer Code Analysis Befund (Sweep 3).

## 7. Root-Cause-Analyse
Developer forgot to add the slowapi decorator.

## 8. Impact
- User: Bekommt unerwartetes Verhalten oder Daten Leak
- Security: Schwäche in API Boundary
- Performance: Möglicher Ressourcenverbrauch

## 9. Fix-Richtung (Strategie, kein Code)
Add `@limiter.limit("20/minute")`.

## 10. Test-Vorschlag
Send 30 search requests rapidly and assert the 21st returns a 429.

## 11. Referenzen
FastAPI Error Handling Docs, OWASP Top 10.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)
> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht erkunden, frag bei Bedarf nach.
>
> **Bug:** Missing Rate Limit in search
> **Datei(en):** backend/api/routers/search.py
> **Aktuelles Verhalten:** No `@limiter.limit` decorator is applied.
> **Erwartetes Verhalten:** Intensive read endpoints should be rate-limited (e.g., 20 requests per minute).
> **Root Cause:** Developer forgot to add the slowapi decorator.
> **Vorgeschlagene Fix-Richtung:** Add `@limiter.limit("20/minute")`.
> **Testfall der danach passen muss:** Send 30 search requests rapidly and assert the 21st returns a 429.
>
> Aktueller Code:
> ```python
> @router.get("/")
async def search(
    q: str = Query(..., min_length=1)
):
> ```
>
> Bitte:
> 1. Minimalen Fix implementieren.
> 2. Regressionstest aus Punkt 10 schreiben.
> 3. Begründen warum dein Fix den Root Cause behebt, nicht nur das Symptom.
> 4. Risiken/Seiteneffekte für mein Review auflisten.
