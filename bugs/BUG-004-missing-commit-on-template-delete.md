# BUG-004: Auskommentierter commit() beim Löschen von Templates in actions/compose.py

- **Severity:** Medium
- **Kategorie:** DB
- **Confidence:** High (statisch erkannt)
- **Erstmals erkannt in:** backend/api/db/crud/templates.py:314
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
In `backend/api/db/crud/templates.py` wurde anscheinend beim Updaten/Refreshen von Templates der Code zum Löschen oder finalen Verwerfen auskommentiert (`# db.delete(template)`, `# db.commit()`). Dies führt im Fehlerfall (oder bei beabsichtigtem Verhalten in diesem Block) dazu, dass Änderungen nicht in die Datenbank geschrieben werden oder Templates nicht aktualisiert werden können. *Hinweis: Hier muss genau der fachliche Kontext geprüft werden, ob das ein Überbleibsel ist.*

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/db/crud/templates.py | 314-316 | Auskommentierter Code |

## 3. Code-Snippet (eingebettet)
```python
// backend/api/db/crud/templates.py:313
    else:
        # db.delete(template)
        # make_transient(template)
        # db.commit()

        template.updated_at = datetime.utcnow()
        template.items = items
```

## 4. Erwartetes Verhalten
Auskommentierter Code, insbesondere im Zusammenhang mit Datenbanktransaktionen, sollte entweder entfernt werden (Dead Code) oder – falls er für die Funktionalität zwingend erforderlich war – wieder aktiviert und korrigiert werden. Die Logik zum Aktualisieren von Templates (`refresh_template`) sollte konsistent sein.

## 5. Tatsächliches Verhalten
Der Code enthält auskommentierte Transaktionsschritte, was darauf hindeutet, dass das Refresh-Verhalten unvollständig refaktoriert wurde.

## 6. Reproduktion
Statische Analyse zeigt auskommentierten Code in einem wichtigen DB-Transaktionsblock.

## 7. Root-Cause-Analyse
Unvollständiges Refactoring.

## 8. Impact
- **User-Impact:** keiner bis potentiell inkonsistente Templates beim Refresh.
- **Daten-Impact:** Inkonsistenzen in der Datenbank.
- **Security-Impact:** keiner.
- **Performance-Impact:** keiner.

## 9. Fix-Richtung (kein Code, nur Strategie)
Analysiere die `refresh_template`-Logik. Entferne den auskommentierten Block, falls er veraltet ist, oder stelle die beabsichtigte Logik wieder her.

## 10. Test-Vorschlag
Kein spezifischer Test, da es sich eher um Dead Code/Code Smell handelt, es sei denn, die Funktionalität von `refresh_template` ist dadurch nachweislich defekt.

## 11. Referenzen
- SQLAlchemy `make_transient`.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.
>
> **Bug:** Auskommentierter Code in Template Refresh Logik
> **Datei(en):** backend/api/db/crud/templates.py
> **Aktuelles Verhalten:** In `refresh_template` sind `db.delete`, `make_transient` und `db.commit` auskommentiert.
> **Erwartetes Verhalten:** Bereinige den Code. Wenn die auskommentierte Logik nicht mehr benötigt wird, entferne sie.
> **Root Cause:** Unvollständiges Refactoring.
> **Vorgeschlagene Fix-Richtung:** Prüfe, ob die Methode ohne den auskommentierten Block korrekt arbeitet, und entferne den toten Code.
> **Testfall der danach passen muss:** Keine.
>
> Aktueller Code:
> ```python
>     else:
>         # db.delete(template)
>         # make_transient(template)
>         # db.commit()
> ```
>
> Bitte:
> 1. Implementiere den Fix mit minimaler Änderung.
> 2. Schreibe den Regressionstest aus §10 (falls zutreffend).
> 3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
> 4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
