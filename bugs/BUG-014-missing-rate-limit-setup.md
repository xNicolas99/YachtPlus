# BUG-014: Missing Rate Limit on Setup

- **Severity:** Medium
- **Kategorie:** Auth
- **Confidence:** High
- **Sweep-Quelle:** 2
- **Erstmals erkannt in:** backend/api/routers/setup/setup.py:101
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
The endpoint to register the first admin user lacks rate limiting, which could allow brute-force attempts to consume resources if left exposed.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/setup/setup.py | 101 | router endpoint |

## 3. Code-Snippet
```python
@router.post("/register")
def register_first_user(
    user_in: schemas.UserCreate,
    db: Session = Depends(get_db)
):
```

## 4. Erwartetes Verhalten
Account creation endpoints should always have rate limiting, even during setup.

## 5. Tatsächliches Verhalten
No rate limiting decorator is present.

## 6. Reproduktion
Statischer Code Analysis Befund (Sweep 2).

## 7. Root-Cause-Analyse
Overlooked because it's a one-time setup endpoint.

## 8. Impact
- User: Bekommt unerwartetes Verhalten oder Daten Leak
- Security: Schwäche in API Boundary
- Performance: Möglicher Ressourcenverbrauch

## 9. Fix-Richtung (Strategie, kein Code)
Add `@limiter.limit("5/minute")`.

## 10. Test-Vorschlag
Send 6 registration requests and assert a 429 response on the last one.

## 11. Referenzen
FastAPI Error Handling Docs, OWASP Top 10.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)
> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht erkunden, frag bei Bedarf nach.
>
> **Bug:** Missing Rate Limit on Setup
> **Datei(en):** backend/api/routers/setup/setup.py
> **Aktuelles Verhalten:** No rate limiting decorator is present.
> **Erwartetes Verhalten:** Account creation endpoints should always have rate limiting, even during setup.
> **Root Cause:** Overlooked because it's a one-time setup endpoint.
> **Vorgeschlagene Fix-Richtung:** Add `@limiter.limit("5/minute")`.
> **Testfall der danach passen muss:** Send 6 registration requests and assert a 429 response on the last one.
>
> Aktueller Code:
> ```python
> @router.post("/register")
def register_first_user(
    user_in: schemas.UserCreate,
    db: Session = Depends(get_db)
):
> ```
>
> Bitte:
> 1. Minimalen Fix implementieren.
> 2. Regressionstest aus Punkt 10 schreiben.
> 3. Begründen warum dein Fix den Root Cause behebt, nicht nur das Symptom.
> 4. Risiken/Seiteneffekte für mein Review auflisten.
