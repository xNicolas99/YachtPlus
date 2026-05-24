# BUG-003: Generic Catch-All in login

- **Severity:** Medium
- **Kategorie:** ErrorHandling
- **Confidence:** High
- **Sweep-Quelle:** 6
- **Erstmals erkannt in:** backend/api/routers/users.py:185
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
The login endpoint has a broad `except Exception as e:` block that masks underlying errors (such as DB connection issues) by throwing a generic HTTP 500.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/users.py | 185 | router endpoint |

## 3. Code-Snippet
```python
    try:
        # login logic
        pass
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
```

## 4. Erwartetes Verhalten
Specific exceptions (e.g., SQLAlchemyError) should be caught specifically.

## 5. Tatsächliches Verhalten
All exceptions are grouped, making debugging difficult and potentially masking authentication bypass vulnerabilities if fail-open occurs.

## 6. Reproduktion
Statischer Code Analysis Befund (Sweep 6).

## 7. Root-Cause-Analyse
Lazy error handling using a catch-all block instead of explicit type checking.

## 8. Impact
- User: Bekommt unerwartetes Verhalten oder Daten Leak
- Security: Schwäche in API Boundary
- Performance: Möglicher Ressourcenverbrauch

## 9. Fix-Richtung (Strategie, kein Code)
Catch specific known exceptions (e.g., DB errors, hashing errors) and let unexpected ones bubble up or map them explicitly.

## 10. Test-Vorschlag
Mock a database timeout during login and verify it raises a specific 503 instead of a generic 500.

## 11. Referenzen
FastAPI Error Handling Docs, OWASP Top 10.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)
> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht erkunden, frag bei Bedarf nach.
>
> **Bug:** Generic Catch-All in login
> **Datei(en):** backend/api/routers/users.py
> **Aktuelles Verhalten:** All exceptions are grouped, making debugging difficult and potentially masking authentication bypass vulnerabilities if fail-open occurs.
> **Erwartetes Verhalten:** Specific exceptions (e.g., SQLAlchemyError) should be caught specifically.
> **Root Cause:** Lazy error handling using a catch-all block instead of explicit type checking.
> **Vorgeschlagene Fix-Richtung:** Catch specific known exceptions (e.g., DB errors, hashing errors) and let unexpected ones bubble up or map them explicitly.
> **Testfall der danach passen muss:** Mock a database timeout during login and verify it raises a specific 503 instead of a generic 500.
>
> Aktueller Code:
> ```python
>     try:
        # login logic
        pass
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
> ```
>
> Bitte:
> 1. Minimalen Fix implementieren.
> 2. Regressionstest aus Punkt 10 schreiben.
> 3. Begründen warum dein Fix den Root Cause behebt, nicht nur das Symptom.
> 4. Risiken/Seiteneffekte für mein Review auflisten.
