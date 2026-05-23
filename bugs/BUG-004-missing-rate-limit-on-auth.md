BUG-004

Severity: Medium
Kategorie: Config
Confidence: Medium
Erstmals erkannt in: backend/api/routers/users.py
Related Bugs: none

1. Zusammenfassung (2–3 Sätze)
Einige Endpoints in `backend/api/routers/users.py`, die sicherheitsrelevant sind, haben kein explizites Rate Limiting. Das betrifft vor allem das Erstellen von API-Keys (`/api/keys/new`). Ohne Rate-Limit kann ein bösartiger (aber authentifizierter) Nutzer den Server mit der Erstellung von unzähligen Schlüsseln fluten (DoS-Risiko / Datenbanküberlastung).

2. Betroffene Stellen
Datei                          Zeile(n)  Rolle
backend/api/routers/users.py 292-306   Hauptort des Bugs (fehlendes @limiter.limit)

3. Code-Snippet (eingebettet)
```python
@router.post("/api/keys/new", response_model=schemas.DisplayAPIKEY)
def create_api_key(
    key: schemas.GenerateAPIKEY,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    name = key.key_name
    auth_check(Authorize)
    # ...
    return crud.create_key(name, user, Authorize, db)
```

4. Erwartetes Verhalten
Endpoint für das Erstellen von Authentifizierungsmitteln (API Keys, Tokens) sollten ein Rate-Limit haben, ähnlich wie es beim `/login` oder `/refresh` umgesetzt ist.

5. Tatsächliches Verhalten
Man kann ohne Begrenzung API-Keys erstellen.

6. Reproduktion
Schritt-für-Schritt, ausführbar:
1. Logge dich ein.
2. Schreibe ein Skript, das in einer Schleife `POST /api/users/api/keys/new` 1000-mal pro Minute aufruft.
3. Der Server blockiert die Requests nicht, die Datenbank wird mit Schlüsseln gefüllt.

7. Root-Cause-Analyse
Es wurde schlichtweg vergessen, den `@limiter.limit(...)` Dekorator zu den entsprechenden Routen in `users.py` hinzuzufügen, vermutlich weil es sich um intern authentifizierte Routen handelt. Jedoch können auch authentifizierte Nutzer durch ein fehlerhaftes Skript oder mutwillig das System überlasten.

8. Impact
User-Impact: Mögliche Beeinträchtigung der API-Performance für alle Nutzer.
Daten-Impact: Die Datenbank wird mit Junk-Daten gefüllt.
Security-Impact: Schwaches DoS-Vektor (Ressourcenerschöpfung).
Performance-Impact: Potenziell hoch unter Last.

9. Fix-Richtung (kein Code, nur Strategie)
Füge `@limiter.limit("5/minute")` oder ein sinnvolles Limit (z.B. `"10/minute"`) zum Endpunkt `/api/keys/new` hinzu. Auch `Request`-Objekt als Parameter hinzufügen, da SlowAPI dies benötigt.

10. Test-Vorschlag
Kein spezifischer Test nötig, aber gut beim manuellen Testen oder im Integrationstest: Schicke 10 Requests auf `/api/keys/new` innerhalb einer Sekunde und prüfe auf `429 Too Many Requests`.

11. Referenzen
Verwandte Funktionen/Module im Repo: backend/api/routers/users.py
Externe Doku falls relevant:

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: Missing Rate Limiting on API Key creation

Aktueller Code:
```python
@router.post("/api/keys/new", response_model=schemas.DisplayAPIKEY)
def create_api_key(
    key: schemas.GenerateAPIKEY,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
```

Bitte:
1. Füge Rate-Limiting hinzu (inkl. `request: Request` Parameter, da SlowAPI diesen braucht).
2. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
3. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
