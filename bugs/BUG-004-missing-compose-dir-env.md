# BUG-004-missing-compose-dir-env

**Severity:** Low
**Kategorie:** Config
**Confidence:** Medium
**Erstmals erkannt in:** `backend/api/settings.py`
**Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)

`settings.COMPOSE_DIR` wird in `backend/api/actions/compose.py` verwendet (z.B. `settings.COMPOSE_DIR + compose.name + "/docker-compose.yml"`). In `Settings` (`backend/api/settings.py`) ist `COMPOSE_DIR` jedoch nicht deklariert. Wenn es dort nicht definiert ist, führt ein Attribut-Zugriff auf `settings.COMPOSE_DIR` zu einem `AttributeError`, was die gesamte Compose-Funktionalität unbrauchbar macht.

## 2. Betroffene Stellen

| Datei                            | Zeile(n) | Rolle                |
| -------------------------------- | -------- | -------------------- |
| backend/api/settings.py          | 60-84    | Fehlendes Attribut `COMPOSE_DIR` in Settings Klasse |
| backend/api/actions/compose.py   | 255      | Aufruf von `settings.COMPOSE_DIR` |

## 3. Code-Snippet (eingebettet)

```python
    with open(settings.COMPOSE_DIR + compose.name + "/docker-compose.yml", "w") as f:
```

## 4. Erwartetes Verhalten

Die Variable `COMPOSE_DIR` sollte in der `Settings` Klasse (z.B. als `COMPOSE_DIR: str = "/compose/"`) deklariert und initialisiert werden.

## 5. Tatsächliches Verhalten

Das Attribut fehlt in der `Settings` Klasse. Jeder Aufruf der `docker-compose` Routen führt wahrscheinlich zu einem internen Serverfehler (500) aufgrund eines `AttributeError`.

## 6. Reproduktion

Starten der Backend-Anwendung und Versuch, einen `docker-compose` Stack anzulegen.

## 7. Root-Cause-Analyse

Bei Pydantic v2 BaseSettings müssen alle in den Modulen verwendeten Eigenschaften in der Klasse deklariert sein.

## 8. Impact

* User-Impact: Fehler beim Anlegen oder Manipulieren von Compose-Projekten.
* Daten-Impact: Keiner.
* Security-Impact: Keiner.
* Performance-Impact: Keiner.

## 9. Fix-Richtung (kein Code, nur Strategie)

Füge in `backend/api/settings.py` der `Settings`-Klasse `COMPOSE_DIR: str = os.getenv("COMPOSE_DIR", "/compose/")` hinzu.

## 10. Test-Vorschlag

Schreibe einen Test, der das Anlegen eines Compose-Projekts simuliert, um sicherzustellen, dass kein AttributeError geworfen wird.

## 11. Referenzen

* `backend/api/settings.py`

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: Das Attribut `COMPOSE_DIR` fehlt in `backend/api/settings.py` innerhalb der `Settings`-Klasse, wird aber von diversen Funktionen in `api/actions/compose.py` referenziert.

Aktueller Code:

```python
class Settings(BaseSettings):
    # Security
    ...
```

Bitte:

1. Füge `COMPOSE_DIR: str = os.getenv("COMPOSE_DIR", "/compose/")` zu der `Settings`-Klasse in `backend/api/settings.py` hinzu.
2. Stelle sicher, dass die Anwendung fehlerfrei startet und Compose-Aktionen nicht mit einem `AttributeError` fehlschlagen.
