# BUG-001: Missing Auth Decorator on get_users

- **Severity:** High
- **Kategorie:** AuthZ
- **Confidence:** High
- **Sweep-Quelle:** 2
- **Erstmals erkannt in:** backend/api/routers/users.py:37
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
The `get_users` endpoint in the users router completely lacks an authentication check. It is accessible to anyone without a token, exposing the entire user list.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/users.py | 37 | router endpoint |

## 3. Code-Snippet
```python
@router.get("/users", response_model=List[schemas.User])
def get_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    users = crud.get_users(db, skip=skip, limit=limit)
```

## 4. Erwartetes Verhalten
The endpoint should verify that the requester is authenticated and holds an admin role.

## 5. Tatsächliches Verhalten
The endpoint executes and returns user data without calling `auth_check(Authorize)` or similar.

## 6. Reproduktion
Statischer Code Analysis Befund (Sweep 2).

## 7. Root-Cause-Analyse
The developer likely forgot to add `auth_check(Authorize)` inside the function body.

## 8. Impact
- User: Bekommt unerwartetes Verhalten oder Daten Leak
- Security: Schwäche in API Boundary
- Performance: Möglicher Ressourcenverbrauch

## 9. Fix-Richtung (Strategie, kein Code)
Add `auth_check(Authorize)` at the beginning of the function.

## 10. Test-Vorschlag
Write a test calling `GET /api/users` without a token and assert a 401 response.

## 11. Referenzen
FastAPI Error Handling Docs, OWASP Top 10.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)
> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht erkunden, frag bei Bedarf nach.
>
> **Bug:** Missing Auth Decorator on get_users
> **Datei(en):** backend/api/routers/users.py
> **Aktuelles Verhalten:** The endpoint executes and returns user data without calling `auth_check(Authorize)` or similar.
> **Erwartetes Verhalten:** The endpoint should verify that the requester is authenticated and holds an admin role.
> **Root Cause:** The developer likely forgot to add `auth_check(Authorize)` inside the function body.
> **Vorgeschlagene Fix-Richtung:** Add `auth_check(Authorize)` at the beginning of the function.
> **Testfall der danach passen muss:** Write a test calling `GET /api/users` without a token and assert a 401 response.
>
> Aktueller Code:
> ```python
> @router.get("/users", response_model=List[schemas.User])
def get_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    users = crud.get_users(db, skip=skip, limit=limit)
> ```
>
> Bitte:
> 1. Minimalen Fix implementieren.
> 2. Regressionstest aus Punkt 10 schreiben.
> 3. Begründen warum dein Fix den Root Cause behebt, nicht nur das Symptom.
> 4. Risiken/Seiteneffekte für mein Review auflisten.
