# BUG-007: Löschen des eigenen Admin-Users (oder des letzten Admins) nicht verhindert

- **Severity:** High
- **Kategorie:** Business
- **Confidence:** High (statisch erkannt)
- **Erstmals erkannt in:** backend/api/routers/users.py:64
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
Der Endpunkt `/users/{user_id}` (`DELETE`) erlaubt es einem Superuser, beliebige Benutzer zu löschen. Es gibt keine Prüfung, die verhindert, dass der Superuser sich selbst löscht, oder dass der letzte verbleibende Superuser im System gelöscht wird. Dies führt zu einem Zustand, in dem sich niemand mehr einloggen und das System verwalten kann.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/users.py | 60-66 | Keine Validierung auf Selbstlöschung oder letzten Admin. |

## 3. Code-Snippet (eingebettet)
```python
// backend/api/routers/users.py:60
    user_to_delete = crud.get_user(db, user_id)
    if not user_to_delete:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user_to_delete)
    db.commit()
    return {"message": "User deleted"}
```

## 4. Erwartetes Verhalten
Bevor ein Benutzer gelöscht wird, muss geprüft werden:
1. Löscht der Benutzer sich selbst? (Wenn ja -> Fehler 400).
2. Ist der zu löschende Benutzer der einzige verbleibende Superuser im System? (Wenn ja -> Fehler 400).

## 5. Tatsächliches Verhalten
Der Benutzer wird ohne diese Prüfungen gelöscht.

## 6. Reproduktion
1. Logge dich als Superuser ein (User ID 1).
2. Sende `DELETE /api/auth/users/1`.
3. Der Benutzer wird gelöscht.
4. Man kann sich nicht mehr einloggen. Das System ist gesperrt.

## 7. Root-Cause-Analyse
Fehlende Business-Logik-Validierung im Delete-Endpunkt.

## 8. Impact
- **User-Impact:** Ein Administrator kann sich versehentlich aussperren.
- **Daten-Impact:** keiner.
- **Security-Impact:** Denial of Service (für die Administrationsebene).
- **Performance-Impact:** keiner.

## 9. Fix-Richtung (kein Code, nur Strategie)
Füge im `delete_user` Router (oder im CRUD) Prüfungen ein:
1. Vergleiche `user.id` (aus JWT) mit `user_id`.
2. Zähle die Anzahl der Superuser in der DB (`db.query(models.User).filter(models.User.is_superuser == True).count()`). Wenn die Anzahl 1 ist und der zu löschende User Superuser ist, lehne ab.

## 10. Test-Vorschlag
Erstelle einen Test, bei dem ein Admin versucht, sich selbst zu löschen, und überprüfe, ob ein 400er Fehler geworfen wird.

## 11. Referenzen
- keine.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.
>
> **Bug:** Löschen des eigenen Admin-Users (oder des letzten Admins) nicht verhindert
> **Datei(en):** backend/api/routers/users.py
> **Aktuelles Verhalten:** Ein Superuser kann sich selbst oder den letzten Superuser löschen.
> **Erwartetes Verhalten:** Es muss verhindert werden, dass sich ein User selbst löscht oder der letzte Superuser gelöscht wird.
> **Root Cause:** Fehlende Business-Logik-Validierung.
> **Vorgeschlagene Fix-Richtung:** Füge in `delete_user` entsprechende If-Abfragen hinzu.
> **Testfall der danach passen muss:** Ein Test, bei dem der Admin sich selbst löscht -> `400 Bad Request`.
>
> Aktueller Code:
> ```python
>     user_to_delete = crud.get_user(db, user_id)
>     if not user_to_delete:
>         raise HTTPException(status_code=404, detail="User not found")
>     db.delete(user_to_delete)
> ```
>
> Bitte:
> 1. Implementiere den Fix mit minimaler Änderung.
> 2. Schreibe den Regressionstest aus §10 (falls zutreffend).
> 3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
> 4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
