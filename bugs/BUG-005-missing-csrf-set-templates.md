# BUG-005: Missing CSRF in set_template_variables

- **Severity:** Medium
- **Kategorie:** Validation
- **Confidence:** Medium
- **Sweep-Quelle:** 3
- **Erstmals erkannt in:** backend/api/routers/app_settings.py:40
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
The endpoint to modify template variables lacks CSRF protection, and due to cookie-based auth, could be vulnerable to cross-site request forgery.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/app_settings.py | 40 | router endpoint |

## 3. Code-Snippet
```python
@router.post(
    "/template-variables",
    response_model=List[schemas.TemplateVariables],
)
def set_template_variables(
    new_variables: List[schemas.TemplateVariables],
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
```

## 4. Erwartetes Verhalten
State-changing POST requests using cookie auth should validate a CSRF token.

## 5. Tatsächliches Verhalten
No CSRF token validation occurs.

## 6. Reproduktion
Statischer Code Analysis Befund (Sweep 3).

## 7. Root-Cause-Analyse
The framework/app lacks global CSRF middleware for cookie-authenticated sessions.

## 8. Impact
- User: Bekommt unerwartetes Verhalten oder Daten Leak
- Security: Schwäche in API Boundary
- Performance: Möglicher Ressourcenverbrauch

## 9. Fix-Richtung (Strategie, kein Code)
Implement SameSite=Strict cookies or a CSRF token verification middleware.

## 10. Test-Vorschlag
Simulate a cross-origin POST request and ensure it is blocked.

## 11. Referenzen
FastAPI Error Handling Docs, OWASP Top 10.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)
> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht erkunden, frag bei Bedarf nach.
>
> **Bug:** Missing CSRF in set_template_variables
> **Datei(en):** backend/api/routers/app_settings.py
> **Aktuelles Verhalten:** No CSRF token validation occurs.
> **Erwartetes Verhalten:** State-changing POST requests using cookie auth should validate a CSRF token.
> **Root Cause:** The framework/app lacks global CSRF middleware for cookie-authenticated sessions.
> **Vorgeschlagene Fix-Richtung:** Implement SameSite=Strict cookies or a CSRF token verification middleware.
> **Testfall der danach passen muss:** Simulate a cross-origin POST request and ensure it is blocked.
>
> Aktueller Code:
> ```python
> @router.post(
    "/template-variables",
    response_model=List[schemas.TemplateVariables],
)
def set_template_variables(
    new_variables: List[schemas.TemplateVariables],
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
> ```
>
> Bitte:
> 1. Minimalen Fix implementieren.
> 2. Regressionstest aus Punkt 10 schreiben.
> 3. Begründen warum dein Fix den Root Cause behebt, nicht nur das Symptom.
> 4. Risiken/Seiteneffekte für mein Review auflisten.
