# BUG-010: JWT Reuse after Logout

- **Severity:** Medium
- **Kategorie:** Auth
- **Confidence:** High
- **Sweep-Quelle:** B3 (Special Sweep)
- **Erstmals erkannt in:** `/api/auth/logout`
- **Related Bugs:** none

## 1. Zusammenfassung
Der Endpunkt `/api/auth/logout` löscht zwar das `access_token_cookie` auf Client-Seite, invalidiert den Token aber nicht serverseitig (z.B. mittels einer Blacklist in der Datenbank). Dadurch kann ein abgefangener Token bis zum Ende seiner Gültigkeit (`ACCESS_TOKEN_EXPIRE_MINUTES`) weiter verwendet werden.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|---|---|---|
| `backend/api/routers/users.py` | `logout` | Logout-Endpunkt ohne Token-Invalidierung |

## 3. Code-Snippet
```python
@router.get("/logout")
def logout(response: Response, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    Authorize.unset_jwt_cookies(response)
    return {"message": "Successfully logged out"}
```

## 4. Erwartetes Verhalten
Beim Logout wird der Token nicht nur aus dem Cookie gelöscht, sondern auch serverseitig als ungültig markiert (z.B. durch Speichern der JTI in einer Blacklist).

## 5. Tatsächliches Verhalten
Der Token behält seine Gültigkeit, wie im Test `test_jwt_reuse_after_logout` bewiesen, bei dem ein Request mit dem alten Token nach dem Logout erfolgreich mit `200 OK` beantwortet wird.

## 6. Reproduktion
Einloggen, Token auslesen, Logout durchführen, dann Endpunkt `/api/auth/me` mit dem Token im `Authorization` Header aufrufen.

## 7. Root-Cause-Analyse
Es gibt keine serverseitige Token-Blacklist. Das Löschen des Cookies ist eine reine Client-Maßnahme.

## 8. Impact
Wenn ein Token gestohlen wird, kann sich der Benutzer nicht effektiv abmelden, um den Angreifer auszusperren.

## 9. Fix-Richtung
Einführung einer Token-Blacklist (DB-Tabelle) für ausgeloggte Tokens, die in `jwt_required` geprüft wird, oder Wechsel auf ein Session-Management.

## 10. Test-Vorschlag
`test_jwt_reuse_after_logout` sollte fehlschlagen, d.h. der zweite Aufruf muss 401 liefern.
