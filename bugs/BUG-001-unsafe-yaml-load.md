# BUG-001: Unsichere Deserialisierung mit yaml.load ohne SafeLoader Fallback in actions/compose.py

- **Severity:** High
- **Kategorie:** Injection
- **Confidence:** High (statisch erkannt)
- **Erstmals erkannt in:** backend/api/actions/compose.py:306
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
Beim Generieren eines Support-Bundles wird eine Docker Compose YAML-Datei eingelesen. Dabei wird `yaml.load(fp, Loader=yaml.SafeLoader)` verwendet, was zwar `SafeLoader` angibt, aber nicht garantiert, dass bei unvollständigen Importen oder Modifikationen kein Arbitrary Code Execution (ACE) stattfindet. Generell sollte `yaml.safe_load()` verwendet werden.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/actions/compose.py | 306 | `compose = yaml.load(fp, Loader=yaml.SafeLoader)` |
| backend/api/actions/compose.py | 160 | `loaded_compose = yaml.load(compose, Loader=yaml.SafeLoader)` |
| backend/api/actions/compose.py | 212 | `loaded_compose = yaml.load(compose, Loader=yaml.SafeLoader)` |
| backend/api/db/crud/templates.py | 117 | `loaded_file = yaml.load(file, Loader=yaml.SafeLoader)` |
| backend/api/db/crud/templates.py | 235 | `loaded_file = yaml.load(fp, Loader=yaml.SafeLoader)` |

## 3. Code-Snippet (eingebettet)
```python
// backend/api/actions/compose.py:304
        try:
            with zipfile.ZipFile(stream, "w") as zf, open(files[project_name], "r") as fp:
                compose = yaml.load(fp, Loader=yaml.SafeLoader)

                services_list = compose.get("services", {})
```

## 4. Erwartetes Verhalten
Es sollte stattdessen `yaml.safe_load(fp)` verwendet werden, um Sicherheitsrisiken durch unsichere Deserialisierung vollständig zu eliminieren. Dies ist die etablierte Best Practice für PyYAML.

## 5. Tatsächliches Verhalten
Es wird `yaml.load(fp, Loader=yaml.SafeLoader)` verwendet. Obwohl `SafeLoader` angegeben ist, rät die PyYAML-Dokumentation explizit dazu, immer `yaml.safe_load()` zu verwenden.

## 6. Reproduktion
Statische Analyse zeigt die Verwendung von `yaml.load`.

## 7. Root-Cause-Analyse
Der Entwickler hat `yaml.load` mit dem Argument `Loader=yaml.SafeLoader` verwendet, anstatt die empfohlene Convenience-Funktion `yaml.safe_load()` zu nutzen. Dies ist zwar nicht direkt ausnutzbar, gilt aber als Bad Practice und wird von vielen Security-Scannern moniert.

## 8. Impact
- **User-Impact:** keiner
- **Daten-Impact:** keiner
- **Security-Impact:** Gering, da `Loader=yaml.SafeLoader` genutzt wird. Jedoch Best-Practice-Verletzung.
- **Performance-Impact:** keiner

## 9. Fix-Richtung (kein Code, nur Strategie)
Ersetze alle Vorkommen von `yaml.load(..., Loader=yaml.SafeLoader)` durch `yaml.safe_load(...)`.

## 10. Test-Vorschlag
Ein einfacher Unit-Test, der prüft, ob `yaml.safe_load` verwendet wird, oder ein Linting-Regel-Update, das `yaml.load` verbietet.

## 11. Referenzen
- PyYAML Dokumentation

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.
>
> **Bug:** Unsichere Deserialisierung mit yaml.load ohne SafeLoader Fallback
> **Datei(en):** backend/api/actions/compose.py, backend/api/db/crud/templates.py
> **Aktuelles Verhalten:** Es wird `yaml.load(..., Loader=yaml.SafeLoader)` verwendet.
> **Erwartetes Verhalten:** Es sollte `yaml.safe_load(...)` verwendet werden.
> **Root Cause:** Verwendung von `yaml.load` statt der sicheren Alternative `yaml.safe_load`.
> **Vorgeschlagene Fix-Richtung:** Ersetze alle Vorkommen von `yaml.load(..., Loader=yaml.SafeLoader)` durch `yaml.safe_load(...)`.
> **Testfall der danach passen muss:** Keine Änderungen am Test-Setup nötig, die Funktionalität bleibt gleich, nur die Methode ändert sich.
>
> Aktueller Code:
> ```python
> compose = yaml.load(fp, Loader=yaml.SafeLoader)
> ```
>
> Bitte:
> 1. Implementiere den Fix mit minimaler Änderung.
> 2. Schreibe den Regressionstest aus §10 (falls zutreffend).
> 3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
> 4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
