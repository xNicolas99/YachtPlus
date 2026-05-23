BUG-002

Severity: Medium
Kategorie: Auth
Confidence: High
Erstmals erkannt in: backend/api/routers/users.py
Related Bugs: none

1. Zusammenfassung (2–3 Sätze)
Der `/refresh`-Endpoint in `backend/api/routers/users.py` verlangt `Authorize.jwt_refresh_token_required()`, ruft in der Implementierung aber `Authorize.get_jwt_subject()` auf, was scheinbar ohne spezifische Prüfung auf einen Refresh-Token-Typ erfolgt. Außerdem überprüft die Funktion nicht, ob der zu erneuernde Nutzer noch in der Datenbank existiert oder gesperrt (`is_active = False`) wurde. Das führt dazu, dass ein deaktivierter oder gelöschter Nutzer mit einem noch gültigen (Refresh-)Token sich endlos neue Access-Token besorgen kann, solange das Refresh-Token gültig ist.

2. Betroffene Stellen
Datei                          Zeile(n)  Rolle
backend/api/routers/users.py 268-278   Hauptort des Bugs (refresh)

3. Code-Snippet (eingebettet)
```python
@router.post("/refresh")
@limiter.limit("20/minute")
def refresh(
    request: Request,
    response: Response,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    current_user = Authorize.get_jwt_subject()
    new_access_token = create_access_token(data={"sub": current_user})
    Authorize.set_access_cookies(new_access_token, response)
    return {"refresh": "successful", "access_token": new_access_token}
```

4. Erwartetes Verhalten
Beim Refreshen eines Tokens muss geprüft werden, ob der Nutzer (aus dem Subject) existiert, noch aktiv ist und ob er gelöscht wurde. Wenn der Nutzer deaktiviert oder gelöscht ist, darf kein neues Token ausgestellt werden.

5. Tatsächliches Verhalten
Der Endpoint stellt bedingungslos ein neues Token aus, solange das vorhandene Token (das vermutlich durch `Depends(get_auth_wrapper)` validiert wurde) noch nicht abgelaufen ist. Ein Admin kann einen Nutzer deaktivieren, aber der Nutzer bleibt über Token-Refreshs weiter im System, bis die Token endgültig ablaufen (bzw. unendlich lange, wenn Refresh-Tokens erneuert werden).

6. Reproduktion
Schritt-für-Schritt, ausführbar:
1. Logge dich als normaler Nutzer ein und erhalte ein Token (bzw. Refresh-Token).
2. Logge dich in einem anderen Fenster als Admin ein und setze den Status des Nutzers auf inaktiv (oder lösche ihn).
3. Rufe als der normale Nutzer den Endpoint `POST /api/users/refresh` auf, sende dabei die entsprechenden Cookies.
4. Du erhältst ein frisches `access_token` und kannst weiter Aktionen durchführen, die nur die Validität des Tokens prüfen. (Viele andere Endpoints prüfen beim `auth_check` nochmal die DB, aber einige vielleicht nicht, oder Token ist trotzdem validiert).

7. Root-Cause-Analyse
Der Refresh-Endpoint vertraut rein auf die Gültigkeit des Krypto-Signatur des übergebenen JWT, ohne den aktuellen Status des Nutzers in der Datenbank nachzuschlagen. Er ist stateless implementiert, während der Zustand der Nutzersperrung zustandsbehaftet in der Datenbank liegt.

8. Impact
User-Impact: Gesperrte/Gelöschte Nutzer können potenziell weiterhin gültige Access-Tokens beziehen.
Daten-Impact: Hängt davon ab, welche Endpoints die DB prüfen. Access-Tokens können missbraucht werden.
Security-Impact: Auth-Bypass (Session Fixation/Revocation failure).
Performance-Impact: Keiner.

9. Fix-Richtung (kein Code, nur Strategie)
In der Funktion `refresh()` sollte der Nutzername aus `current_user` in der Datenbank nachgeschlagen werden. Wenn der Nutzer nicht existiert oder nicht `is_active` ist, sollte ein Fehler 401 geworfen werden (und idealerweise die Cookies gelöscht werden).

10. Test-Vorschlag
Erstelle einen Nutzer, logge ihn ein, speichere das Token. Deaktiviere den Nutzer in der Datenbank. Versuche dann, mit dem gespeicherten Token den `/refresh`-Endpoint aufzurufen. Es sollte ein 401 zurückkommen.

11. Referenzen
Verwandte Funktionen/Module im Repo: backend/api/routers/users.py, backend/api/utils/security.py
Externe Doku falls relevant:

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: JWT Refresh does not validate user status (active/exists)

Aktueller Code:
```python
@router.post("/refresh")
@limiter.limit("20/minute")
def refresh(
    request: Request,
    response: Response,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    current_user = Authorize.get_jwt_subject()
    new_access_token = create_access_token(data={"sub": current_user})
    Authorize.set_access_cookies(new_access_token, response)
    return {"refresh": "successful", "access_token": new_access_token}
```

Bitte:
1. Implementiere den Fix mit minimaler Änderung (z.B. Session holen, Nutzer laden, prüfen).
2. Schreibe den Regressionstest aus §10.
3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
