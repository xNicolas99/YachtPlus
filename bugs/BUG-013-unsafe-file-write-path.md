# BUG-013: Unsafe file write path

- **Severity:** Medium
- **Kategorie:** Injection
- **Confidence:** Medium
- **Sweep-Quelle:** 2
- **Erstmals erkannt in:** backend/api/routers/setup/setup.py:53
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
When marking setup as completed, the file write path relies on an environment variable without sanitizing it against path traversal.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/setup/setup.py | 53 | router endpoint |

## 3. Code-Snippet
```python
def mark_setup_completed():
    try:
        with open(SETUP_FLAG_FILE, "w") as f:
            f.write("Setup completed")
```

## 4. Erwartetes Verhalten
The application should ensure `SETUP_FLAG_FILE` is strictly an absolute path within an allowed directory.

## 5. Tatsächliches Verhalten
If `SETUP_FLAG_FILE` is maliciously configured, it can overwrite arbitrary files.

## 6. Reproduktion
Statischer Code Analysis Befund (Sweep 2).

## 7. Root-Cause-Analyse
Trusting configuration variables for file operations without validation.

## 8. Impact
- User: Bekommt unerwartetes Verhalten oder Daten Leak
- Security: Schwäche in API Boundary
- Performance: Möglicher Ressourcenverbrauch

## 9. Fix-Richtung (Strategie, kein Code)
Use `os.path.abspath` and verify it resides within `/app/data/`.

## 10. Test-Vorschlag
Set the environment variable to `../../etc/passwd` and assert the app refuses to write.

## 11. Referenzen
FastAPI Error Handling Docs, OWASP Top 10.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)
> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht erkunden, frag bei Bedarf nach.
>
> **Bug:** Unsafe file write path
> **Datei(en):** backend/api/routers/setup/setup.py
> **Aktuelles Verhalten:** If `SETUP_FLAG_FILE` is maliciously configured, it can overwrite arbitrary files.
> **Erwartetes Verhalten:** The application should ensure `SETUP_FLAG_FILE` is strictly an absolute path within an allowed directory.
> **Root Cause:** Trusting configuration variables for file operations without validation.
> **Vorgeschlagene Fix-Richtung:** Use `os.path.abspath` and verify it resides within `/app/data/`.
> **Testfall der danach passen muss:** Set the environment variable to `../../etc/passwd` and assert the app refuses to write.
>
> Aktueller Code:
> ```python
> def mark_setup_completed():
    try:
        with open(SETUP_FLAG_FILE, "w") as f:
            f.write("Setup completed")
> ```
>
> Bitte:
> 1. Minimalen Fix implementieren.
> 2. Regressionstest aus Punkt 10 schreiben.
> 3. Begründen warum dein Fix den Root Cause behebt, nicht nur das Symptom.
> 4. Risiken/Seiteneffekte für mein Review auflisten.
