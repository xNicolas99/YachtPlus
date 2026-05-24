# BUG-006: Unsafe Upload in import_settings

- **Severity:** High
- **Kategorie:** Validation
- **Confidence:** High
- **Sweep-Quelle:** 3
- **Erstmals erkannt in:** backend/api/routers/app_settings.py:65
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
The import settings file upload parses uploaded data (JSON/YAML) without fully validating its structure, which could lead to deserialization vulnerabilities or logic bypasses.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/app_settings.py | 65 | router endpoint |

## 3. Code-Snippet
```python
@router.post("/import", response_model=schemas.ImportSettingsResponse)
def import_settings(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    content = file.file.read()
    # parse content without strict schema validation
```

## 4. Erwartetes Verhalten
Uploaded data should be parsed into a strict Pydantic model before processing.

## 5. Tatsächliches Verhalten
Data is read and partially trusted, potentially overwriting internal config unexpectedly.

## 6. Reproduktion
Statischer Code Analysis Befund (Sweep 3).

## 7. Root-Cause-Analyse
Missing structural validation layer between upload and application logic.

## 8. Impact
- User: Bekommt unerwartetes Verhalten oder Daten Leak
- Security: Schwäche in API Boundary
- Performance: Möglicher Ressourcenverbrauch

## 9. Fix-Richtung (Strategie, kein Code)
Parse the uploaded content directly into a strict Pydantic model.

## 10. Test-Vorschlag
Upload a maliciously formatted JSON payload and assert a 422 Unprocessable Entity.

## 11. Referenzen
FastAPI Error Handling Docs, OWASP Top 10.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)
> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht erkunden, frag bei Bedarf nach.
>
> **Bug:** Unsafe Upload in import_settings
> **Datei(en):** backend/api/routers/app_settings.py
> **Aktuelles Verhalten:** Data is read and partially trusted, potentially overwriting internal config unexpectedly.
> **Erwartetes Verhalten:** Uploaded data should be parsed into a strict Pydantic model before processing.
> **Root Cause:** Missing structural validation layer between upload and application logic.
> **Vorgeschlagene Fix-Richtung:** Parse the uploaded content directly into a strict Pydantic model.
> **Testfall der danach passen muss:** Upload a maliciously formatted JSON payload and assert a 422 Unprocessable Entity.
>
> Aktueller Code:
> ```python
> @router.post("/import", response_model=schemas.ImportSettingsResponse)
def import_settings(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    content = file.file.read()
    # parse content without strict schema validation
> ```
>
> Bitte:
> 1. Minimalen Fix implementieren.
> 2. Regressionstest aus Punkt 10 schreiben.
> 3. Begründen warum dein Fix den Root Cause behebt, nicht nur das Symptom.
> 4. Risiken/Seiteneffekte für mein Review auflisten.
