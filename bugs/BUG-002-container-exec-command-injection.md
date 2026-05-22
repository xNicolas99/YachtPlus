# BUG-002: Command Injection in WebSocket exec (shlex.split mit user-controlled shell string)

- **Severity:** High
- **Kategorie:** Injection
- **Confidence:** High (statisch erkannt)
- **Erstmals erkannt in:** backend/api/routers/containers.py:214
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
Der WebSocket-Endpoint für `container_exec` nimmt einen Query-Parameter `shell` entgegen und übergibt diesen direkt an `shlex.split(shell)`, bevor er an `container.exec(cmd=...)` weitergegeben wird. Dies ermöglicht eine Argument-Injection, wenn ein Angreifer eine präparierte Zeichenkette übergibt.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/containers.py | 213-214 | `exec_instance = await container.exec(cmd=shlex.split(shell), ...)` |

## 3. Code-Snippet (eingebettet)
```python
// backend/api/routers/containers.py:213
        exec_instance = await container.exec(
            cmd=shlex.split(shell),
            stdin=True,
            stdout=True,
            stderr=True,
            privileged=False,
            tty=True
        )
```

## 4. Erwartetes Verhalten
Da es sich um einen Terminal-Exec-Endpoint handelt, muss die Shell (meist `/bin/sh` oder `/bin/bash`) strikt validiert oder gegen eine Allowlist geprüft werden. Eine freie Eingabe des Befehls ermöglicht es dem Client, beliebige Argumente zu injizieren.

## 5. Tatsächliches Verhalten
Der Parameter `shell` wird vom Client ohne serverseitige Einschränkung akzeptiert und nur durch `shlex.split()` getrennt. Dies kann missbraucht werden, um Kommandos mit ungewollten Argumenten zu starten.

## 6. Reproduktion
1. Initiiere eine WebSocket-Verbindung zu `/api/containers/{container_id}/exec?shell=/bin/sh+-c+malicious_command`
2. Beobachte, wie der Befehl im Container ausgeführt wird.

## 7. Root-Cause-Analyse
Der Parameter `shell` ist benutzerkontrolliert und wird nicht auf eine Allowlist (z. B. `["/bin/sh", "/bin/bash", "sh", "bash"]`) beschränkt.

## 8. Impact
- **User-Impact:** Angreifer mit Container-Zugriff können beliebige Befehle ausführen.
- **Daten-Impact:** Potentielle Datenkompromittierung innerhalb des Containers.
- **Security-Impact:** High. Dies ist eine Arbitrary Command Execution im Kontext des Containers.
- **Performance-Impact:** keiner.

## 9. Fix-Richtung (kein Code, nur Strategie)
Führe eine Allowlist für den `shell`-Parameter ein (z. B. `allowed_shells = ["/bin/sh", "/bin/bash", "sh", "bash"]`). Wenn der Parameter nicht in der Liste ist, verwende einen sicheren Default (z. B. `/bin/sh`) oder lehne die Anfrage ab.

## 10. Test-Vorschlag
Erstelle einen Testfall, der versucht, einen ungültigen `shell`-Befehl (z. B. `echo "hacked"`) an den WebSocket-Endpoint zu senden, und stelle sicher, dass dieser abgewiesen oder auf `/bin/sh` zurückgefallen wird.

## 11. Referenzen
- Aiodocker Dokumentation zur `exec`-Methode.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.
>
> **Bug:** Command Injection in WebSocket exec (shlex.split)
> **Datei(en):** backend/api/routers/containers.py
> **Aktuelles Verhalten:** Der Parameter `shell` wird ungeprüft via `shlex.split(shell)` ausgeführt.
> **Erwartetes Verhalten:** Der `shell`-Parameter muss validiert werden (Allowlist).
> **Root Cause:** Fehlende Validierung/Einschränkung von benutzerdefinierten Eingaben für Befehle.
> **Vorgeschlagene Fix-Richtung:** Führe eine Allowlist für erlaubte Shells ein (`/bin/sh`, `/bin/bash` etc.) und validiere die Eingabe.
> **Testfall der danach passen muss:** Test für die Abweisung ungültiger Shell-Befehle im WebSocket.
>
> Aktueller Code:
> ```python
>         exec_instance = await container.exec(
>             cmd=shlex.split(shell),
> ```
>
> Bitte:
> 1. Implementiere den Fix mit minimaler Änderung.
> 2. Schreibe den Regressionstest aus §10.
> 3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
> 4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
