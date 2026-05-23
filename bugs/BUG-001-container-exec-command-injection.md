BUG-001

Severity: High
Kategorie: Injection
Confidence: High
Erstmals erkannt in: backend/api/routers/containers.py
Related Bugs: none

1. Zusammenfassung (2–3 Sätze)
Die WebSocket-Endpoint für Container-Exec in `backend/api/routers/containers.py` übergibt das vom User kontrollierte `shell`-Parameter an `shlex.split`, aber es erlaubt die Injektion von beliebigen Kommando-Flags (z.B. für den exec-Aufruf). Zwar verhindert `shlex.split()` grundlegende Shell-Injections in einer lokalen Shell, aber hier wird es direkt als `cmd` Liste an Docker weitergegeben, wodurch ein Angreifer eine andere Binary mit beliebigen Argumenten im Container ausführen kann. Es fehlt die Validierung des `shell`-Parameters gegen eine erlaubte Whitelist oder ein Regex.

2. Betroffene Stellen
Datei                          Zeile(n)  Rolle
backend/api/routers/containers.py 174-177   Hauptort des Bugs
backend/api/routers/containers.py 254-262   Aufrufer

3. Code-Snippet (eingebettet)
```python
@router.websocket("/{container_id}/exec")
async def container_exec(
    websocket: WebSocket,
    container_id: str,
    shell: str = Query("/bin/sh"),
# ...
        exec_instance = await container.exec(
            cmd=shlex.split(shell),
# ...
```

4. Erwartetes Verhalten
Der `shell`-Parameter sollte auf erlaubte Werte (z.B. `/bin/sh`, `/bin/bash`, `sh`, `bash`) validiert werden. Die Übergabe an `cmd` sollte nicht zulassen, dass Nutzer beliebige Kommandos in einem Container ausführen, auf den sie nur Shell-Zugriff haben sollen (auch wenn sie den Container starten/stoppen dürfen).

5. Tatsächliches Verhalten
Nutzer mit der Berechtigung, einen Container zu starten, können den WebSocket aufrufen und als `shell`-Queryparameter z.B. `/bin/echo "hacked" > /tmp/hack` oder ähnliches übergeben, was dann im Containerkontext als exec ausgeführt wird.

6. Reproduktion
Schritt-für-Schritt, ausführbar:
1. Logge dich als normaler Nutzer mit `perm_start` ein.
2. Baue eine WebSocket-Verbindung zu `ws://localhost:8080/api/containers/<id>/exec?shell=/bin/touch%20/tmp/hacked` auf.
3. Überprüfe den Container: Es wird eine Datei `/tmp/hacked` im Container angelegt.

7. Root-Cause-Analyse
Der Parameter `shell` ist komplett unkontrolliert. Er ist als "Shell" gedacht, wird aber als das auszuführende Kommando (plus Argumente) an die Docker API weitergereicht. Ein Nutzer mit Exec-Berechtigung kann somit jedes beliebige Kommando im Container ausführen, nicht nur eine Shell starten. Das verletzt das Principle of Least Privilege, auch wenn der Nutzer den Container starten/stoppen kann.

8. Impact
User-Impact: Nutzer mit `perm_start` auf einen Container können beliebige Prozesse im Container ausführen, ohne eine Shell-Sitzung zu starten.
Daten-Impact: Mögliche Korruption/Leak von Daten im Container.
Security-Impact: Command Injection im Kontext des Containers.
Performance-Impact: Keiner.

9. Fix-Richtung (kein Code, nur Strategie)
Füge eine Whitelist für erlaubte Shell-Werte im Endpoint hinzu (z.B. `["/bin/sh", "/bin/bash", "sh", "bash"]`). Wenn der `shell`-Parameter nicht in der Whitelist ist, gib einen Fehler 400 (bzw. close websocket code 1008) zurück.

10. Test-Vorschlag
Ein Test sollte versuchen, eine WebSocket-Verbindung mit `shell="invalid_shell"` herzustellen und prüfen, ob die Verbindung abgelehnt wird (Close-Code 1008). Ein weiterer Test sollte eine erlaubte Shell überprüfen (z.B. `/bin/sh`).

11. Referenzen
Verwandte Funktionen/Module im Repo: backend/api/routers/containers.py
Externe Doku falls relevant:

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: Potential Container Exec Command Injection via WebSocket Shell Parameter

Aktueller Code:
```python
@router.websocket("/{container_id}/exec")
async def container_exec(
    websocket: WebSocket,
    container_id: str,
    shell: str = Query("/bin/sh"),
# ...
        exec_instance = await container.exec(
            cmd=shlex.split(shell),
# ...
```

Bitte:
1. Implementiere den Fix mit minimaler Änderung.
2. Schreibe den Regressionstest aus §10.
3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
