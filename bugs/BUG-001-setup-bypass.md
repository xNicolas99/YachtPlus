# BUG-001

Severity: High
Kategorie: Auth
Confidence: High (statisch erkannt)
Erstmals erkannt in: backend/api/routers/setup/setup.py
Related Bugs: none

1. Zusammenfassung (2–3 Sätze)
Die Funktion `bypass_setup` erlaubt es, das Setup als "bypassed" zu markieren, solange noch keine Benutzer in der Datenbank existieren. Da jedoch nach diesem Bypass `is_setup_completed(db)` True zurückliefert, schlagen alle zukünftigen Versuche fehl, `register_first_user` aufzurufen, was das System aussperrt (Catch-22).

2. Betroffene Stellen
Datei: backend/api/routers/setup/setup.py
Zeilen: 63-78
Rolle: Hauptort des Bugs

3. Code-Snippet
```python
@router.post("/bypass")
def bypass_setup(db: Session = Depends(get_db)):
    if is_setup_completed(db):
        return {"message": "Setup already completed or bypassed."}

    if db.query(User).count() > 0:
        raise HTTPException(status_code=400, detail="Cannot bypass setup after a user has been registered.")

    status = db.query(SetupStatus).first()
    if not status:
        status = SetupStatus(is_bypassed=True)
        db.add(status)
    else:
        status.is_bypassed = True
    db.commit()

    return {"message": "Setup bypassed"}
```

4. Erwartetes Verhalten
Wenn das Setup umgangen wird, sollte es eine Möglichkeit geben, sich entweder ohne Auth anzumelden oder einen Admin-User über CLI/Env zu erstellen, oder die Funktion sollte gar nicht existieren/anders designed sein.

5. Tatsächliches Verhalten
Wenn das Setup umgangen wird, wird `is_setup_completed` True, was bedeutet, dass `/register` `403 Setup already completed` wirft. Da kein User existiert, ist niemand in der Lage, Accounts zu erstellen oder sich einzuloggen.

6. Reproduktion
Schritt-für-Schritt:
1. Rufe `POST /api/setup/bypass` bei frischer DB auf.
2. Versuche `POST /api/setup/register`.
Beobachtung: 403 Forbidden. Man ist ausgesperrt.

7. Root-Cause-Analyse
`bypass_setup` setzt den gleichen Status, der `/register` blockiert, erstellt aber keinen Admin-User.

8. Impact
User-Impact: Neue Nutzer können die App nicht nutzen.
Daten-Impact: keiner
Security-Impact: Denial of Service für das Setup.
Performance-Impact: keiner

9. Fix-Richtung
Entferne den Bypass-Endpunkt oder erstelle beim Bypass einen Default-User/erfordere eine Alternative. Da `DISABLE_AUTH` existiert, ist `bypass_setup` in dieser Form vermutlich fehlerhaft konzipiert oder überflüssig. Wenn es nur für Tests gedacht ist, sollte es hinter `DISABLE_AUTH` stehen.

10. Test-Vorschlag
Ein Test sollte sicherstellen, dass nach `/bypass` entweder ein Login möglich ist oder `/register` nicht fälschlicherweise dauerhaft gesperrt wird ohne Alternative.

11. Referenzen
Verwandte Funktionen: `register_first_user` in `backend/api/routers/setup/setup.py`

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: setup_bypass blockiert spätere Registrierungen komplett.

Aktueller Code:
```python
@router.post("/bypass")
def bypass_setup(db: Session = Depends(get_db)):
    if is_setup_completed(db):
        return {"message": "Setup already completed or bypassed."}

    if db.query(User).count() > 0:
        raise HTTPException(status_code=400, detail="Cannot bypass setup after a user has been registered.")

    status = db.query(SetupStatus).first()
    if not status:
        status = SetupStatus(is_bypassed=True)
        db.add(status)
    else:
        status.is_bypassed = True
    db.commit()

    return {"message": "Setup bypassed"}
```

Bitte:
1. Implementiere den Fix mit minimaler Änderung. Überlege, ob bypass_setup überhaupt sinnvoll ist.
2. Schreibe den Regressionstest aus §10.
3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
