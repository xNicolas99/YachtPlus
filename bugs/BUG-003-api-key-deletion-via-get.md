BUG-003

Severity: Medium
Kategorie: Other
Confidence: High
Erstmals erkannt in: backend/api/routers/users.py
Related Bugs: none

1. Zusammenfassung (2–3 Sätze)
Der Endpoint zum Löschen (bzw. Blacklisten) eines API-Keys ist fälschlicherweise als HTTP `GET` anstatt als `DELETE` registriert. Dadurch ist die Löschaktion nicht idempotent und verstößt gegen gängige REST-Prinzipien. Außerdem könnte dies durch Prefetching-Mechanismen im Browser oder Caching versehentlich ausgelöst werden, was zu unbeabsichtigtem Löschen von API-Keys führt (CSRF per Image-Tag o.ä., falls die Authentifizierung via Cookie läuft, was hier der Fall ist).

2. Betroffene Stellen
Datei                          Zeile(n)  Rolle
backend/api/routers/users.py 308-317   Hauptort des Bugs (Registrierung als @router.get)

3. Code-Snippet (eingebettet)
```python
@router.get("/api/keys/{key_id}")
def delete_api_key(
    key_id, db: Session = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    username = Authorize.get_jwt_subject()
    requester = crud.get_user_by_name(db=db, username=username) if username else None
    if not requester:
        raise HTTPException(status_code=401, detail="Not logged in.")
    return crud.blacklist_api_key(key_id, db, requesting_user=requester)
```

4. Erwartetes Verhalten
Der Endpoint für das Löschen einer Ressource mit Seiteneffekten sollte die HTTP-Methode `DELETE` (oder zumindest `POST`) verwenden.

5. Tatsächliches Verhalten
Die Route ist als `@router.get("/api/keys/{key_id}")` registriert. Ein einfacher `GET`-Request (z. B. durch einen Link, ein Bild-Tag `<img src="/api/keys/1">` auf einer bösartigen Seite, während der User eingeloggt ist) löst das Löschen/Blacklisten des API-Keys aus (CSRF-Vektor, da Cookies standardmäßig mitgesendet werden, wenn SameSite nicht strikt gesetzt ist oder Browser-Limits umgangen werden).

6. Reproduktion
Schritt-für-Schritt, ausführbar:
1. Logge dich ein.
2. Erstelle einen API-Key und notiere dessen ID (z.B. `1`).
3. Öffne im Browser einfach die URL `http://localhost:8080/api/users/api/keys/1` (bzw. sende einen simplen GET-Request dorthin).
4. Der API-Key wird gelöscht/geblacklistet, was als Antwort bestätigt wird.

7. Root-Cause-Analyse
Ein Copy-Paste- oder Tippfehler bei der Router-Dekoration: `@router.get` statt `@router.delete`. Dies ist ein Verstoß gegen REST und öffnet die Tür für CSRF-ähnliches Verhalten, da GET-Requests keine Preflight-Prüfungen durchlaufen und oft blind ausgeführt werden können.

8. Impact
User-Impact: API-Keys können versehentlich gelöscht werden (z. B. durch Klicken auf Links).
Daten-Impact: Verlust von API-Zugängen.
Security-Impact: Schwacher CSRF-Vektor für API-Key-Löschung (obwohl SameOrigin/SameSite oft schützt, ist es Best-Practice-Verletzung).
Performance-Impact: Keiner.

9. Fix-Richtung (kein Code, nur Strategie)
Ändere den Router-Dekorator für `delete_api_key` von `@router.get` zu `@router.delete`.

10. Test-Vorschlag
Erstelle einen API-Key. Führe einen `DELETE`-Request gegen `/api/users/api/keys/{key_id}` aus und überprüfe den 200er Status sowie das erfolgreiche Löschen. Führe testweise einen `GET`-Request auf dieselbe URL aus, der nun fehlschlagen sollte (405 Method Not Allowed).

11. Referenzen
Verwandte Funktionen/Module im Repo: backend/api/routers/users.py
Externe Doku falls relevant:

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: API Key deletion uses HTTP GET method instead of DELETE

Aktueller Code:
```python
@router.get("/api/keys/{key_id}")
def delete_api_key(
    key_id, db: Session = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
# ...
    return crud.blacklist_api_key(key_id, db, requesting_user=requester)
```

Bitte:
1. Implementiere den Fix mit minimaler Änderung (nur Dekoration auf `@router.delete` ändern).
2. Schreibe den Regressionstest aus §10 (sofern Tests in `tests/test_users.py` o.ä. existieren).
3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll (z. B. ob das Frontend auch angepasst werden muss, da es evtl. GET nutzt).
