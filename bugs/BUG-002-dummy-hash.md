# BUG-002-dummy-hash

**Severity:** Low
**Kategorie:** Other
**Confidence:** High (statisch erkannt)
**Erstmals erkannt in:** `backend/api/routers/users.py`
**Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)

Semgrep warnt vor einem festkodierten bcrypt-Hash (`_TIMING_DUMMY_BCRYPT_HASH`). Dieser Hash ist jedoch ausdrücklich (laut Kommentar) ein "Dummy"-Hash, der verwendet wird, um Timing-Angriffe zu verhindern. Ein legitimer Use-Case.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|---|---|---|
| `backend/api/routers/users.py` | 31 | Hauptort des Bugs |

## 3. Code-Snippet (eingebettet)
```python
_TIMING_DUMMY_BCRYPT_HASH = "$2b$12$EPB.k0Vz4T5lXl6uT9f9/eG0m7b7mG3aR4jPq4s0q3wY0r7U5/7qC"
```

## 4. Erwartetes Verhalten
False Positive, es wird kein Verhalten erwartet.

## 5. Tatsächliches Verhalten
False Positive, verhält sich wie erwartet.

## 6. Reproduktion
Schritt-für-Schritt, ausführbar:
`N/A`

## 7. Root-Cause-Analyse
Scanner False-Positive.

## 8. Impact
User-Impact: keiner
Daten-Impact: keiner
Security-Impact: keiner
Performance-Impact: keiner

## 9. Fix-Richtung (kein Code, nur Strategie)
Kein Fix notwendig, evtl. # nosec anhängen.

## 10. Test-Vorschlag
Kein Test notwendig.

## 11. Referenzen
Verwandte Funktionen/Module im Repo: `backend/api/routers/users.py`

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: False Positive Hardcoded Hash

Aktueller Code:
```python
_TIMING_DUMMY_BCRYPT_HASH = "$2b$12$EPB.k0Vz4T5lXl6uT9f9/eG0m7b7mG3aR4jPq4s0q3wY0r7U5/7qC"
```

Bitte:
Ignoriere den Report, es ist ein False-Positive.
