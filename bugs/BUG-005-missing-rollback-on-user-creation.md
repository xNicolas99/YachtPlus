# BUG-005: Fehlendes db.rollback() bei Fehler in create_user

- **Severity:** Medium
- **Kategorie:** ErrorHandling / DB
- **Confidence:** High (statisch erkannt)
- **Erstmals erkannt in:** backend/api/db/crud/users.py:79
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
In `backend/api/db/crud/users.py` in der Methode `update_user` fehlt im `except Exception`-Block ein `db.rollback()`. Wenn die Datenbank beim `db.commit()` einen Fehler wirft (z.B. Integritätsverletzung), bleibt die Session in einem fehlerhaften Zustand und Folgeanfragen im selben Thread/Kontext könnten fehlschlagen.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/db/crud/users.py | 79-80 | Im `try-except` um `db.commit()` fehlt das `rollback`. |

## 3. Code-Snippet (eingebettet)
```python
// backend/api/db/crud/users.py:75
        try:
            db.add(_user)
            db.commit()
            db.refresh(_user)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=exc)
```

## 4. Erwartetes Verhalten
Bei einem Fehler während `db.commit()` muss zwingend `db.rollback()` aufgerufen werden, bevor die Exception weitergeworfen wird.

## 5. Tatsächliches Verhalten
Das `rollback` fehlt, die Session ist potentiell blockiert.

## 6. Reproduktion
1. Führe ein Update eines Users durch, das eine DB-Constraint verletzt (z. B. auf einen bereits existierenden Username).
2. Der Server wirft einen 400er Fehler.
3. Danach könnten weitere DB-Anfragen mit `PendingRollbackError` fehlschlagen.

## 7. Root-Cause-Analyse
Der Exception-Handler fängt den Fehler zwar, räumt die Session aber nicht auf.

## 8. Impact
- **User-Impact:** Potentielle API-Fehler für nachfolgende Anfragen.
- **Daten-Impact:** keiner.
- **Security-Impact:** keiner.
- **Performance-Impact:** keiner.

## 9. Fix-Richtung (kein Code, nur Strategie)
Füge `db.rollback()` im `except`-Block vor dem `raise` hinzu.

## 10. Test-Vorschlag
Simuliere einen DB-Fehler beim Update eines Users und stelle sicher, dass die Datenbank-Session danach noch funktioniert.

## 11. Referenzen
- SQLAlchemy Session Management.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.
>
> **Bug:** Fehlendes db.rollback() bei Fehler in update_user
> **Datei(en):** backend/api/db/crud/users.py
> **Aktuelles Verhalten:** Im `except`-Block um `db.commit()` in `update_user` fehlt `db.rollback()`.
> **Erwartetes Verhalten:** `db.rollback()` muss aufgerufen werden, bevor die Exception geworfen wird.
> **Root Cause:** Unvollständiges Exception Handling.
> **Vorgeschlagene Fix-Richtung:** Füge `db.rollback()` hinzu.
> **Testfall der danach passen muss:** Keine (unit test falls einfach mockbar).
>
> Aktueller Code:
> ```python
>         except Exception as exc:
>             raise HTTPException(status_code=400, detail=exc)
> ```
>
> Bitte:
> 1. Implementiere den Fix mit minimaler Änderung.
> 2. Schreibe den Regressionstest aus §10 (falls zutreffend).
> 3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
> 4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
