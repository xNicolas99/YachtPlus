# BUG-015: Masked Exception in file write

- **Severity:** Medium
- **Kategorie:** ErrorHandling
- **Confidence:** High
- **Sweep-Quelle:** 6
- **Erstmals erkannt in:** backend/api/routers/setup/setup.py:55
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
If the setup flag file cannot be written (e.g., due to permission errors), the exception is entirely swallowed without logging or halting.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/setup/setup.py | 55 | router endpoint |

## 3. Code-Snippet
```python
    try:
        with open(SETUP_FLAG_FILE, "w") as f:
            f.write("Setup completed")
    except Exception:
        pass
```

## 4. Erwartetes Verhalten
Critical state changes failing should result in an error or at least a log warning.

## 5. Tatsächliches Verhalten
The setup completes logically but the flag is not persisted, causing setup to trigger again on reboot.

## 6. Reproduktion
Statischer Code Analysis Befund (Sweep 6).

## 7. Root-Cause-Analyse
Using `except Exception: pass` as a quick workaround for potential read-only filesystems.

## 8. Impact
- User: Bekommt unerwartetes Verhalten oder Daten Leak
- Security: Schwäche in API Boundary
- Performance: Möglicher Ressourcenverbrauch

## 9. Fix-Richtung (Strategie, kein Code)
Log the error securely `logger.error("Failed to persist setup flag.")`.

## 10. Test-Vorschlag
Mock `open` to raise a PermissionError and verify a log message is generated.

## 11. Referenzen
FastAPI Error Handling Docs, OWASP Top 10.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)
> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht erkunden, frag bei Bedarf nach.
>
> **Bug:** Masked Exception in file write
> **Datei(en):** backend/api/routers/setup/setup.py
> **Aktuelles Verhalten:** The setup completes logically but the flag is not persisted, causing setup to trigger again on reboot.
> **Erwartetes Verhalten:** Critical state changes failing should result in an error or at least a log warning.
> **Root Cause:** Using `except Exception: pass` as a quick workaround for potential read-only filesystems.
> **Vorgeschlagene Fix-Richtung:** Log the error securely `logger.error("Failed to persist setup flag.")`.
> **Testfall der danach passen muss:** Mock `open` to raise a PermissionError and verify a log message is generated.
>
> Aktueller Code:
> ```python
>     try:
        with open(SETUP_FLAG_FILE, "w") as f:
            f.write("Setup completed")
    except Exception:
        pass
> ```
>
> Bitte:
> 1. Minimalen Fix implementieren.
> 2. Regressionstest aus Punkt 10 schreiben.
> 3. Begründen warum dein Fix den Root Cause behebt, nicht nur das Symptom.
> 4. Risiken/Seiteneffekte für mein Review auflisten.
