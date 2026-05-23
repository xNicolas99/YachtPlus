# BUG-004: Potenzielles Binden an alle Interfaces (0.0.0.0)

- **Severity:** Medium
- **Kategorie:** Config
- **Confidence:** Medium (statisch erkannt durch Bandit)
- **Erstmals erkannt in:** api/actions/apps.py:112
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
Beim Verarbeiten von Compose-Projekten oder App-Deployments (`api/actions/apps.py`) wird potenziell hartkodiert `0.0.0.0` als Standard-IP für Container-Ports verwendet (`p.get("IP", "0.0.0.0")`). Dies führt dazu, dass gestartete Container ihre Ports auf allen Host-Netzwerkschnittstellen (inkl. öffentlichen) freigeben, anstatt nur lokal (`127.0.0.1`), falls keine IP explizit angegeben wurde.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/actions/apps.py | 112 | Fallback-IP beim Port-Parsing |

## 3. Code-Snippet (eingebettet)
```python
// backend/api/actions/apps.py:111

        host_ip = p.get("IP", "0.0.0.0")
        host_port = str(p.get("PublicPort", ""))
```

## 4. Erwartetes Verhalten
Je nach Sicherheitsanforderung sollte der Standard-Bind für Container-Ports nicht zwingend `0.0.0.0` sein, oder zumindest sollte dies dem Administrator über eine Env-Variable konfigurierbar gemacht werden. Wenn ein Container Ports exponiert, ohne dass der User das explizit auf `0.0.0.0` fordert, ist es sicherer, Standardmäßig an `127.0.0.1` oder eine interne Docker-IP zu binden, um ungewollte Exposition ins Internet zu verhindern.

## 5. Tatsächliches Verhalten
Fehlt die IP im Port-Binding-Dictionary, wird standardmäßig `0.0.0.0` verwendet.

## 6. Reproduktion
Statisch nachgewiesen durch Bandit (Fehlercode B104).
Wenn ein Benutzer ein App-Template nutzt, das nur Ports spezifiziert (z.B. `8080:80`), wird dies beim Parsen der existierenden Container-Konfigurationen intern als Binding auf `0.0.0.0:8080` abgebildet.

## 7. Root-Cause-Analyse
Standardverhalten von Docker wird hier explizit im Code als Fallback (`0.0.0.0`) nachgebildet. Zwar ist das das Docker-Standardverhalten, es kann aber bei unbedachter Nutzung dazu führen, dass interne Dienste (z.B. eine Datenbank eines App-Templates) weltweit erreichbar sind.

## 8. Impact
- **User-Impact:** Keine Funktionsstörung.
- **Daten-Impact:** Potenzieller Datenleak, wenn App-Komponenten (Datenbanken, Caches) unbeabsichtigt öffentlich zugänglich gemacht werden.
- **Security-Impact:** Erhöhte Angriffsfläche.

## 9. Fix-Richtung (kein Code, nur Strategie)
Falls dieser Code nur den bestehenden Zustand *ausliest* (z.B. von `docker inspect`), ist es kein direktes Deployment-Problem, sondern nur ein Anzeige-Fallback. Ist es jedoch Teil der Start-Logik, sollte geprüft werden, ob `0.0.0.0` durch eine konfigurierbare Variable ersetzt werden kann. (Da Bandit dies meldet, sollte zumindest ein `# nosec B104` hinzugefügt werden, wenn das Verhalten beabsichtigt und sicher ist, andernfalls das Fallback anpassen).

## 10. Test-Vorschlag
Kein spezifischer Test nötig, aber eine Überprüfung der Port-Binding-Logik bei App-Deployments, um sicherzustellen, dass keine unsicheren Defaults angewendet werden.

## 11. Referenzen
- Verwandte Funktionen/Module im Repo: `backend/api/actions/apps.py`

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier.
>
> **Bug:** Potenzielles Binden an alle Interfaces (0.0.0.0)
> **Datei(en):** backend/api/actions/apps.py
> **Aktuelles Verhalten:** `p.get("IP", "0.0.0.0")` verwendet hartkodiert alle Interfaces als Fallback.
> **Erwartetes Verhalten:** Kläre, ob dies ein reiner Lese-Fallback (z.B. aus `docker inspect`) ist. Falls ja, kommentiere mit `# nosec B104` und einer Erklärung. Falls es den Container-Start beeinflusst, mache es konfigurierbar oder ändere es auf `127.0.0.1`.
> **Root Cause:** Bandit meldet B104 bei hardcoded 0.0.0.0, was zu ungewollter Exposition führen kann.
> **Vorgeschlagene Fix-Richtung:** Prüfe den Kontext. Wenn beabsichtigt -> `# nosec B104` an der Zeile anbringen.
>
> Aktueller Code:
> ```python
>         host_ip = p.get("IP", "0.0.0.0")
> ```
>
> Bitte:
> 1. Implementiere den Fix.
