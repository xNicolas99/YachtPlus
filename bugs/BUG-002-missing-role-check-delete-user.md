# BUG-002: Missing Role Check in delete_user

- **Severity:** High
- **Kategorie:** AuthZ
- **Confidence:** High
- **Sweep-Quelle:** 2
- **Erstmals erkannt in:** backend/api/routers/users.py:55
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
The `delete_user` endpoint checks for authentication using `auth_check`, but fails to ensure the requester is an admin or the owner of the account before deletion.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/users.py | 55 | router endpoint |

## 3. Code-Snippet
```python
@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    crud.delete_user(db=db, user_id=user_id)
```

## 4. Erwartetes Verhalten
Only an admin or the user themselves should be able to delete an account.

## 5. Tatsächliches Verhalten
Any authenticated user can delete any other user's account via their ID (BOLA/IDOR).

## 6. Reproduktion
Statischer Code Analysis Befund (Sweep 2).

## 7. Root-Cause-Analyse
Missing role verification logic after the basic authentication check.

## 8. Impact
- User: Bekommt unerwartetes Verhalten oder Daten Leak
- Security: Schwäche in API Boundary
- Performance: Möglicher Ressourcenverbrauch

## 9. Fix-Richtung (Strategie, kein Code)
Retrieve the requester's user object and compare their role/ID before proceeding.

## 10. Test-Vorschlag
Login as a standard user, attempt to delete another user's ID, and assert a 403 Forbidden response.

## 11. Referenzen
FastAPI Error Handling Docs, OWASP Top 10.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)
> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht erkunden, frag bei Bedarf nach.
>
> **Bug:** Missing Role Check in delete_user
> **Datei(en):** backend/api/routers/users.py
> **Aktuelles Verhalten:** Any authenticated user can delete any other user's account via their ID (BOLA/IDOR).
> **Erwartetes Verhalten:** Only an admin or the user themselves should be able to delete an account.
> **Root Cause:** Missing role verification logic after the basic authentication check.
> **Vorgeschlagene Fix-Richtung:** Retrieve the requester's user object and compare their role/ID before proceeding.
> **Testfall der danach passen muss:** Login as a standard user, attempt to delete another user's ID, and assert a 403 Forbidden response.
>
> Aktueller Code:
> ```python
> @router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    crud.delete_user(db=db, user_id=user_id)
> ```
>
> Bitte:
> 1. Minimalen Fix implementieren.
> 2. Regressionstest aus Punkt 10 schreiben.
> 3. Begründen warum dein Fix den Root Cause behebt, nicht nur das Symptom.
> 4. Risiken/Seiteneffekte für mein Review auflisten.
