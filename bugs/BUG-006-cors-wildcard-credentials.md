# BUG-006: CORS Erlaubt Credentials mit potenziell wildcards/ungesicherten Origins (Suspicion)

- **Severity:** Suspicion
- **Kategorie:** Config
- **Confidence:** Low (Vermutung, hängt von der Default-Konfiguration ab)
- **Erstmals erkannt in:** backend/api/main.py:53
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
In `backend/api/main.py` wird die `CORSMiddleware` konfiguriert. Sie akzeptiert `allow_credentials=True` zusammen mit `allow_origins=get_settings().CORS_ORIGINS`. Wenn in `get_settings().CORS_ORIGINS` ein Wildcard (`*`) oder ein ungesicherter Host eingetragen ist, stellt dies ein massives Sicherheitsrisiko (Credentials Leak) dar. Die Default-Werte in `settings.py` sind auf `localhost` beschränkt, aber es gibt keine Validierung in `settings.py`, um Wildcards abzulehnen, wenn ein User `YACHT_CORS_ORIGINS=*` in die `.env` schreibt.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/main.py | 51-56 | CORS Middleware Config |
| backend/api/settings.py | 58 | Parst `YACHT_CORS_ORIGINS` |

## 3. Code-Snippet (eingebettet)
```python
// backend/api/main.py:50
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 4. Erwartetes Verhalten
Wenn `allow_credentials=True` gesetzt ist, DARF `allow_origins` kein `["*"]` enthalten. Die Pydantic-Settings sollten validieren, dass `*` nicht in der Liste der konfigurierten CORS-Origins auftaucht.

## 5. Tatsächliches Verhalten
Es gibt keine Validierung auf `*` in den Settings.

## 6. Reproduktion
1. Setze in `.env`: `YACHT_CORS_ORIGINS=*`
2. Die App startet und das Backend antwortet auf CORS-Anfragen von beliebigen Seiten, obwohl Credentials erlaubt sind. (FastAPI weigert sich oft selbst, wenn `*` und credentials gesetzt sind, wirft dann aber einen 500er beim Start).

## 7. Root-Cause-Analyse
Fehlende Input-Validierung für ENV-Variablen in `settings.py`.

## 8. Impact
- **User-Impact:** keiner.
- **Daten-Impact:** keiner.
- **Security-Impact:** Potentieller Credentials-Leak bei Fehlkonfiguration.
- **Performance-Impact:** keiner.

## 9. Fix-Richtung (kein Code, nur Strategie)
Füge in `api/settings.py` einen Validator (mit Pydantic `@field_validator` oder `@validator`) für `CORS_ORIGINS` hinzu, der explizit prüft, ob `*` enthalten ist, und in diesem Fall eine Exception wirft, die den Start der App verhindert.

## 10. Test-Vorschlag
Versuche, die App mit `YACHT_CORS_ORIGINS=*` zu starten, und erwarte einen Validierungsfehler.

## 11. Referenzen
- FastAPI CORS Dokumentation.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.
>
> **Bug:** CORS Erlaubt Credentials mit Wildcards
> **Datei(en):** backend/api/settings.py
> **Aktuelles Verhalten:** `YACHT_CORS_ORIGINS` wird ohne Validierung übernommen.
> **Erwartetes Verhalten:** Wenn `YACHT_CORS_ORIGINS` ein `*` enthält, muss der Start mit einem Fehler abgebrochen werden (da `allow_credentials=True` gesetzt ist).
> **Root Cause:** Fehlende Validierung der Umgebungsvariablen.
> **Vorgeschlagene Fix-Richtung:** Füge in `settings.py` einen Validator für `CORS_ORIGINS` hinzu, der `*` verbietet.
> **Testfall der danach passen muss:** Keine.
>
> Aktueller Code:
> ```python
> CORS_ORIGINS: list = os.getenv("YACHT_CORS_ORIGINS", ...).split(",")
> ```
>
> Bitte:
> 1. Implementiere den Fix mit minimaler Änderung.
> 2. Schreibe den Regressionstest aus §10 (falls zutreffend).
> 3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
> 4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
