# BUG-001: Beliebige Codeausführung via Container-Start (Arbitrary Container Run)

- **Severity:** Critical
- **Kategorie:** Injection
- **Confidence:** High (statisch erkannt durch Semgrep, Blockierendes Issue)
- **Erstmals erkannt in:** api/actions/apps.py:381
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
Beim Starten eines neuen Containers durch die Funktion `deploy_app` (oder ähnliche) in `api/actions/apps.py` werden ungeprüfte Benutzereingaben (wie Image-Name, Command, Mounts und Environment Variables) direkt an den Docker Daemon übergeben. Dies erlaubt es einem authentifizierten Angreifer, Container mit beliebigen Images auszuführen, Host-Pfade (z. B. `/`) zu mounten und so vollständigen Root-Zugriff auf das Host-System zu erlangen (Container Escape / RCE).

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/actions/apps.py | 381-390 | Direkter Aufruf der Docker SDK run-Methode mit User-Input |

## 3. Code-Snippet (eingebettet)
```python
// backend/api/actions/apps.py:381
        launch = dclient.containers.run(
            name=name,
            image=image,
            restart_policy=restart_policy,
            command=command,
            ports=ports,
            network=network,
            network_mode=network_mode,
            volumes=volumes,
            environment=env,
            detach=True
        )
```

## 4. Erwartetes Verhalten
Bevor Parameter an den Docker Daemon (`dclient.containers.run()`) übergeben werden, müssen Image-Namen (Whitelist/Validierung), Mounts (Verhindern von `/`-Mounts oder Host-Directory-Traversal) und Command-Strings strikt validiert und sanitisiert werden. Alternativ darf dieser Endpunkt nur für vertrauenswürdige, vordefinierte Vorlagen nutzbar sein.

## 5. Tatsächliches Verhalten
Die App-Details (z. B. aus einem geparsten Compose-File oder Template) werden direkt in Parameter für die Docker API übersetzt. Ein Angreifer kann ein App-Template so modifizieren, dass es z. B. `/` auf `/host` mountet und einen Command wie `chroot /host /bin/bash -c "echo 'attacker_ssh_key' >> /root/.ssh/authorized_keys"` ausführt. Da der Docker-Socket gemountet ist, geschieht dies mit den Rechten des Docker Daemons (idR. Root auf dem Host).

## 6. Reproduktion
Schritt-für-Schritt, statisch nachgewiesen durch Semgrep (`python.docker.security.audit.docker-arbitrary-container-run`).
Die Ausführung erfolgt über einen App-Deployment-Endpunkt.
1. Authentifiziere als Benutzer mit Rechten zum App-Deploy.
2. Erstelle ein Payload (z. B. Custom App Template oder Compose), das das Image `alpine:latest` nutzt, `/` auf `/host` mountet und als Command `touch /host/tmp/pwned` enthält.
3. Sende die Deploy-Anfrage an die API.
4. Der Container startet und schreibt die Datei auf das Host-System.

## 7. Root-Cause-Analyse
Es fehlt an Input-Validierung und Autorisierung an der Grenze zwischen API-Input und Docker-API-Aufruf. Die Anwendung vertraut den Eingaben aus Templates/Requests vollständig und nutzt sie als Parameter für sicherheitskritische Docker-SDK-Methoden.

## 8. Impact
- **User-Impact:** Alle User/Dienste auf dem Host-System.
- **Daten-Impact:** Vollständiger Kompromittierung des Host-Dateisystems (Leak, Korruption, Manipulation).
- **Security-Impact:** Remote Code Execution (RCE) / Privilege Escalation vom Container zum Host-Root.
- **Performance-Impact:** Potenziell Denial of Service, wenn bösartige Container Ressourcen blockieren.

## 9. Fix-Richtung (kein Code, nur Strategie)
Führe eine strenge Schema-Validierung (z.B. Pydantic) für App-Deployment-Parameter ein. Beschränke erlaubte Volumes auf ein dediziertes Datenverzeichnis und blockiere Host-Mounts (wie `/`, `/etc`, `/var/run/docker.sock`, etc.) kategorisch. Commands müssen über `shlex.split` geparst und validiert werden. Image-Namen müssen validiert werden (keine unerwünschten Registries).

## 10. Test-Vorschlag
Schreibe einen Test (z. B. `test_deploy_app_blocks_host_mount`), der versucht, eine App mit einem Volume-Mount `/` -> `/host` zu deployen. Dieser Request muss mit einem 400 Bad Request oder 403 Forbidden abgelehnt werden, bevor die Docker-API aufgerufen wird. Ein weiterer Test soll sicherstellen, dass Commands sicher geparst werden.

## 11. Referenzen
- Verwandte Funktionen/Module im Repo: `backend/api/actions/apps.py`
- Externe Doku falls relevant: https://sg.run/pxEL

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.
>
> **Bug:** Beliebige Codeausführung via Container-Start (Arbitrary Container Run)
> **Datei(en):** backend/api/actions/apps.py
> **Aktuelles Verhalten:** Ungeprüfte Benutzereingaben werden direkt an `dclient.containers.run()` übergeben, was Host-Kompromittierung via bösartigen Mounts und Commands erlaubt.
> **Erwartetes Verhalten:** Vor dem Aufruf müssen Mount-Pfade (z. B. Verbot von Host-Root `/`), Images und Commands strikt validiert werden.
> **Root Cause:** Fehlende Validierungsschicht zwischen User-Input (App Templates) und der sicherheitskritischen Docker-API.
> **Vorgeschlagene Fix-Richtung:** Implementiere in `api/actions/apps.py` vor dem `containers.run` Aufruf eine Validierung. Blockiere Host-Mounts (insb. `/`, `/etc`, `/var`) und parse Commands sicher.
> **Testfall der danach passen muss:** Ein Test, der ein Deploy mit Mount `/` versucht, muss fehlschlagen (400/403).
>
> Aktueller Code:
> ```python
>         launch = dclient.containers.run(
>             name=name,
>             image=image,
>             restart_policy=restart_policy,
>             command=command,
>             ports=ports,
>             network=network,
>             network_mode=network_mode,
>             volumes=volumes,
>             environment=env,
>             detach=True
>         )
> ```
>
> Bitte:
> 1. Implementiere den Fix mit minimaler Änderung.
> 2. Schreibe den Regressionstest aus §10.
> 3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
> 4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
