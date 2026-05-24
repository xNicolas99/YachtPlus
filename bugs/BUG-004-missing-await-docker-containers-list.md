# BUG-004: Unawaited coroutine in Docker containers list

- **Severity:** High
- **Kategorie:** Concurrency / BusinessLogic
- **Confidence:** High
- **Sweep-Quelle:** B2-S6 (Mechanical Sweep)
- **Erstmals erkannt in:** Unbekannt (aus SQLAlchemy Instance Processor getriggert)
- **Related Bugs:** none

## 1. Zusammenfassung
Während des Mechanical Sweeps wurde eine `RuntimeWarning: coroutine 'DockerContainers.list' was never awaited` protokolliert. Dies deutet darauf hin, dass ein Aufruf der asynchronen Methode `docker.containers.list()` in `aiodocker` in einem synchronen Kontext (z.B. einem SQLAlchemy Model Property oder einem synchronen Background-Job) erfolgt, ohne auf das Ergebnis zu warten.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|---|---|---|
| Unbekannt | (in Log gezeigt aus `sqlalchemy/orm/loading.py:812`) | Aufruf von `docker.containers.list()` |

## 3. Code-Snippet
Nicht exakt bestimmbar ohne tiefere Code-Analyse, vermutlich in einem Model-Property (z.B. `@property def status(self)` das asynchron auflöst) oder in einer der API-Routen, wo das Ergebnis eines synchronen Mappings nicht awaited wird.

## 4. Erwartetes Verhalten
Keine unawaited Coroutines im Log. Methoden, die asynchrone SDKs aufrufen, müssen korrekt mit `await` aufgelöst werden.

## 5. Tatsächliches Verhalten
```python
/home/jules/.pyenv/versions/3.12.13/lib/python3.12/site-packages/sqlalchemy/orm/loading.py:812: RuntimeWarning: coroutine 'DockerContainers.list' was never awaited
```

## 6. Reproduktion
Wurde durch den Mechanischen Sweep auf `/api/setup/generate_2fa` oder ähnlichen Endpunkten getriggert, aber der Callstack im Pytest-Warning zeigt auf SQLAlchemy.

## 7. Root-Cause-Analyse
Es gibt wahrscheinlich ein Pydantic Schema oder SQLAlchemy Model (z.B. `App` oder `Template`), das beim Serialisieren eine asynchrone Funktion aufruft, aber da Serializer in FastAPI/Pydantic synchron arbeiten, wird das await vergessen oder ist nicht möglich.

## 8. Impact
BusinessLogic: Container-Status oder andere Laufzeit-Details werden nicht korrekt im API-Response geladen und stattdessen wird das String-Repräsentation des Coroutine-Objekts (oder N/A) zurückgegeben.

## 9. Fix-Richtung
Das Laden von Container-Status aus Docker darf nicht in synchronen ORM-Properties passieren. Die Daten müssen im API-Router explizit asynchron geladen (`await docker.containers.list()`) und dann als separates Feld oder als aggregiertes DTO an die Responses übergeben werden.

## 10. Test-Vorschlag
Regelmäßige Pytest Runs prüfen, dass keine `RuntimeWarning: coroutine ... was never awaited` emittiert wird.
