# BUG-004: Missing Auth in read_template_variables

- **Severity:** High
- **Kategorie:** AuthZ
- **Confidence:** High
- **Sweep-Quelle:** 2
- **Erstmals erkannt in:** backend/api/routers/app_settings.py:28
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
The endpoint to read sensitive template variables does not verify the caller's identity or permissions.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/app_settings.py | 28 | router endpoint |

## 3. Code-Snippet
```python
@router.get(
    "/template-variables",
    response_model=List[schemas.TemplateVariables],
)
def read_template_variables(
    db: Session = Depends(get_db)
):
```

## 4. Erwartetes Verhalten
Reading template variables should require authentication.

## 5. Tatsächliches Verhalten
Anyone can read potentially sensitive deployment template variables.

## 6. Reproduktion
Statischer Code Analysis Befund (Sweep 2).

## 7. Root-Cause-Analyse
Omitted the `Authorize: get_auth_wrapper` dependency and `auth_check` call.

## 8. Impact
- User: Bekommt unerwartetes Verhalten oder Daten Leak
- Security: Schwäche in API Boundary
- Performance: Möglicher Ressourcenverbrauch

## 9. Fix-Richtung (Strategie, kein Code)
Add `Authorize: get_auth_wrapper = Depends(get_auth_wrapper)` and call `auth_check(Authorize)`.

## 10. Test-Vorschlag
Request the endpoint without an access token and assert a 401 error.

## 11. Referenzen
FastAPI Error Handling Docs, OWASP Top 10.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)
> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht erkunden, frag bei Bedarf nach.
>
> **Bug:** Missing Auth in read_template_variables
> **Datei(en):** backend/api/routers/app_settings.py
> **Aktuelles Verhalten:** Anyone can read potentially sensitive deployment template variables.
> **Erwartetes Verhalten:** Reading template variables should require authentication.
> **Root Cause:** Omitted the `Authorize: get_auth_wrapper` dependency and `auth_check` call.
> **Vorgeschlagene Fix-Richtung:** Add `Authorize: get_auth_wrapper = Depends(get_auth_wrapper)` and call `auth_check(Authorize)`.
> **Testfall der danach passen muss:** Request the endpoint without an access token and assert a 401 error.
>
> Aktueller Code:
> ```python
> @router.get(
    "/template-variables",
    response_model=List[schemas.TemplateVariables],
)
def read_template_variables(
    db: Session = Depends(get_db)
):
> ```
>
> Bitte:
> 1. Minimalen Fix implementieren.
> 2. Regressionstest aus Punkt 10 schreiben.
> 3. Begründen warum dein Fix den Root Cause behebt, nicht nur das Symptom.
> 4. Risiken/Seiteneffekte für mein Review auflisten.
