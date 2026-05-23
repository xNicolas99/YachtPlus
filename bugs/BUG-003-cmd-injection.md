# BUG-003-cmd-injection

**Severity:** Critical
**Kategorie:** Injection
**Confidence:** High (reproduziert durch Code-Analyse)
**Erstmals erkannt in:** `backend/api/actions/compose.py`
**Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)

Die Funktion `validate_app_name` verbietet zwar leading hyphens und underscores, die Funktion `_compose_app_action_sync` übergibt den Parameter `action` allerdings unvalidiert an `_run_compose_command`, welches `subprocess.run(["docker-compose", action, ...])` aufruft. Dadurch kann ein Angreifer durch Setzen von `action` auf einen Options-Flag (z.B. `--file` oder ähnliches, oder gar Befehls-Injections über shell=False mit entsprechenden Flags) den docker-compose Befehl manipulieren.

## 2. Betroffene Stellen

| Datei                            | Zeile(n) | Rolle                |
| -------------------------------- | -------- | -------------------- |
| backend/api/actions/compose.py   | 131-137  | Aufruf von _run_compose_command mit unvalidiertem `action` |
| backend/api/actions/compose.py   | 36       | Ausführung in subprocess.run |

## 3. Code-Snippet (eingebettet)

```python
    if action == "up":
        output = _run_compose_command(["up", "-d", app], _cwd, full_env)
    elif action == "create":
        output = _run_compose_command(["up", "--no-start", app], _cwd, full_env)
    elif action == "rm":
        output = _run_compose_command(["rm", "--force", "--stop", app], _cwd, full_env)
    else:
        output = _run_compose_command([action, app], _cwd, full_env)
```

## 4. Erwartetes Verhalten

Der Parameter `action` sollte strikt gegen eine Whitelist validiert werden (z.B. `up`, `down`, `start`, `stop`, `restart`, `pause`, `unpause`, `rm`), damit keine unautorisierten Docker-Compose Parameter oder Flags übergeben werden können.

## 5. Tatsächliches Verhalten

Da `action` in den `else`-Zweig fällt, wird es ungefiltert an `subprocess.run` übergeben. Wenn `action` beispielsweise `--help` oder Optionen wie `--file /etc/passwd` entspricht (zusammen mit einem passenden App-Namen), könnte das Command Line Parsing von `docker-compose` unerwartetes Verhalten zeigen. Schlimmer noch, Angreifer können Command-Line-Flags injizieren.

## 6. Reproduktion

Schritt-für-Schritt, ausführbar:

```bash
# Beispiel-Request
curl -X POST "http://localhost:8000/api/compose/my_project/apps/my_app/--help"
```

## 7. Root-Cause-Analyse

Die API erlaubt dynamische `action`-Routen, prüft den Parameter aber nicht über eine Allowlist. Dadurch rutschen alle unbekannten Werte in den `else`-Block und werden direkt als Argument für das Binary `docker-compose` eingesetzt.

## 8. Impact

* User-Impact: Jeder authentifizierte Nutzer mit Zugriffsrechten.
* Daten-Impact: Potenzielle Ausweitung der Privilegien im Kontext des `docker-compose` Aufrufs oder Auslesen lokaler Dateien (je nach `docker-compose` Optionen).
* Security-Impact: Argument Injection.
* Performance-Impact: keiner.

## 9. Fix-Richtung (kein Code, nur Strategie)

Füge in `_compose_app_action_sync` (und in `_compose_action_sync`) eine strikte Validierung des `action`-Parameters hinzu. Definiere ein Set zulässiger Aktionen (z.B. `ALLOWED_ACTIONS = {"up", "create", "rm", "start", "stop", "restart", "pause", "unpause", "pull", "logs"}`). Falls `action` nicht in diesem Set enthalten ist, löse direkt eine `HTTPException(400)` aus.

## 10. Test-Vorschlag

Es sollte ein Test geschrieben werden, der versucht, Parameter-Injection über den `action`-Wert durchzuführen. Der Test sollte sicherstellen, dass Werte wie `--version` oder `--help` mit einem 400 Bad Request abgelehnt werden.

## 11. Referenzen

* Verwandte Funktionen/Module im Repo: `api/actions/compose.py`

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: In `api/actions/compose.py` ist der `action`-Parameter anfällig für Argument-Injection, da er unvalidiert als Argument an `docker-compose` in `subprocess.run` übergeben wird.

Aktueller Code:

```python
    if action == "up":
        output = _run_compose_command(["up", "-d", app], _cwd, full_env)
    elif action == "create":
        output = _run_compose_command(["up", "--no-start", app], _cwd, full_env)
    elif action == "rm":
        output = _run_compose_command(["rm", "--force", "--stop", app], _cwd, full_env)
    else:
        output = _run_compose_command([action, app], _cwd, full_env)
```

Bitte:

1. Implementiere den Fix mit minimaler Änderung. Füge eine Whitelist `ALLOWED_ACTIONS` (inkl. `start`, `stop`, `restart`, `pull`, `pause`, `unpause` etc.) hinzu und lehne unbekannte Actions ab.
2. Überprüfe, ob die Whitelist in `_compose_action_sync` und `_compose_app_action_sync` angewendet wird.
3. Schreibe einen Regressionstest, der sicherstellt, dass ungültige `action`-Werte abgewiesen werden.
4. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
5. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
