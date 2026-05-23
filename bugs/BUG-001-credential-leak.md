# BUG-001-credential-leak

**Severity:** Low
**Kategorie:** Logging
**Confidence:** High (statisch erkannt)
**Erstmals erkannt in:** `backend/api/routers/containers.py`
**Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)

Ein Logger gibt potenziell den JWT Payload bei fehlschlagenden WebSockets aus, ist jedoch in diesem speziellen Fall der "sub" Claim, welcher typischerweise der Benutzername ist, keine echte Verschlusssache oder Secret. Dennoch ist der Semgrep-Scanner hier angeschlagen, was auf eine falsche Benutzung hindeutet. Wahrscheinlicher Leak von sensitivem Token Payload wurde durch Code Review widerlegt. Es bleibt ein Logging Issue (False Positive), welches ignoriert werden kann.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|---|---|---|
| `backend/api/routers/containers.py` | 236 | Hauptort des Bugs |

## 3. Code-Snippet (eingebettet)
```python
        if claims.get("setup_pending"):
            logger.warning(
                "WebSocket exec rejected: setup_pending token for user %s",
                claims.get("sub"),
            )
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
Verwandte Funktionen/Module im Repo: `backend/api/routers/containers.py`

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: False Positive Logging Warning

Aktueller Code:
```python
        if claims.get("setup_pending"):
            logger.warning(
                "WebSocket exec rejected: setup_pending token for user %s",
                claims.get("sub"),
            )
```

Bitte:
Ignoriere den Report, es ist ein False-Positive.
