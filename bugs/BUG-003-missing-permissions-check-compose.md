# BUG-003: Fehlende Berechtigungsprüfung für Compose-Aktionen

- **Severity:** High
- **Kategorie:** AuthZ
- **Confidence:** High (statisch erkannt)
- **Erstmals erkannt in:** backend/api/routers/compose.py:27
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
In `backend/api/routers/compose.py` wird nur `auth_check(Authorize)` aufgerufen. Diese Funktion stellt sicher, dass der Benutzer eingeloggt ist, prüft jedoch keine spezifischen Berechtigungen (wie `perm_manage_compose`, falls eine existiert, oder allgemeine Start/Stop/Restart-Rechte). Da in YachtPlus feingranulare Berechtigungen für User vorgesehen sind (siehe `backend/api/db/crud/users.py:37` für `perm_start`, `perm_stop` etc.), führt das Fehlen von `check_permission` dazu, dass JEDER eingeloggte Benutzer Compose-Projekte verwalten kann.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/compose.py | 27-46 | Endpunkte wie `/{project_name}/actions/{action}` und `/{project_name}/edit` prüfen nur `auth_check`. |

## 3. Code-Snippet (eingebettet)
```python
// backend/api/routers/compose.py:26
@router.get("/{project_name}/actions/{action}")
async def get_compose_action(project_name, action, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    if action not in ["up", "down", "start", "stop", "restart", "create", "delete", "pull"]:
        raise HTTPException(status_code=400, detail="Invalid action")
    if action == "delete":
        return await delete_compose(project_name)
    else:
        return await compose_action(project_name, action)
```

## 4. Erwartetes Verhalten
Bei Aktionen wie `start`, `stop`, `restart`, `delete` oder dem Bearbeiten von Compose-Projekten muss die spezifische Berechtigung des Benutzers geprüft werden. Zumindest sollten schreibende/ausführende Endpunkte auf `check_permission` (z. B. `check_permission("perm_start", Authorize, db)`) zurückgreifen.

## 5. Tatsächliches Verhalten
Jeder Benutzer mit einem gültigen JWT kann Compose-Projekte hoch-/herunterfahren und löschen.

## 6. Reproduktion
1. Logge dich als Standardbenutzer (ohne Admin-Rechte) ein.
2. Sende einen GET-Request an `/api/compose/{project_name}/actions/delete`.
3. Das Projekt wird gelöscht.

## 7. Root-Cause-Analyse
Der Endpunkt verlässt sich nur auf `auth_check`, welches lediglich die Token-Validität sicherstellt. Die Überprüfung der feingranularen Berechtigungen (wie in `auth.py` mit `check_permission` vorgesehen) fehlt.

## 8. Impact
- **User-Impact:** Privilege Escalation (Jeder kann alles machen).
- **Daten-Impact:** Datenverlust (Projekte können von unbefugten Usern gelöscht werden).
- **Security-Impact:** High.
- **Performance-Impact:** keiner.

## 9. Fix-Richtung (kein Code, nur Strategie)
Füge `check_permission("perm_<action>", Authorize, db)` oder eine äquivalente Admin-/Permission-Prüfung zu den entsprechenden Endpunkten in `compose.py` und anderen betroffenen Routern hinzu. Die Datenbank-Session (`db`) muss als Dependency übergeben werden.

## 10. Test-Vorschlag
Erstelle einen Test, bei dem ein regulärer Benutzer (ohne z. B. `perm_delete`) versucht, ein Compose-Projekt zu löschen, und stelle sicher, dass ein 403 Forbidden zurückgegeben wird.

## 11. Referenzen
- `backend/api/auth/auth.py` -> `check_permission`

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.
>
> **Bug:** Fehlende Berechtigungsprüfung für Compose-Aktionen
> **Datei(en):** backend/api/routers/compose.py
> **Aktuelles Verhalten:** Endpunkte wie `/{project_name}/actions/{action}` prüfen nur auf Anwesenheit eines Tokens (`auth_check(Authorize)`), nicht auf spezifische Rechte.
> **Erwartetes Verhalten:** Je nach Aktion (`start`, `stop`, `delete`) muss `check_permission(...)` aufgerufen werden.
> **Root Cause:** Fehlende Implementierung der feingranularen Rechtekontrolle an den API-Grenzen.
> **Vorgeschlagene Fix-Richtung:** Injecte die `db` Dependency und rufe `check_permission` für die entsprechenden Aktionen auf (z.B. `perm_start`, `perm_delete`).
> **Testfall der danach passen muss:** Ein Test, der prüft, ob ein User ohne Rechte ein Projekt löschen kann.
>
> Aktueller Code:
> ```python
> @router.get("/{project_name}/actions/{action}")
> async def get_compose_action(project_name, action, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
>     auth_check(Authorize)
> ```
>
> Bitte:
> 1. Implementiere den Fix mit minimaler Änderung.
> 2. Schreibe den Regressionstest aus §10.
> 3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
> 4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
