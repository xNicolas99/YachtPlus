BUG-005

Severity: High
Kategorie: Other
Confidence: High
Erstmals erkannt in: backend/api/db/crud/templates.py
Related Bugs: none

1. Zusammenfassung (2–3 Sätze)
Die Funktion `validate_url` in `backend/api/db/crud/templates.py` soll SSRF verhindern, indem sie IPs blockiert, die lokal oder privat sind. Wenn jedoch ein unresolvierbarer Hostname (z. B. eine Phantasie-Domain) übergeben wird, schlägt `socket.getaddrinfo` fehl und fällt in den `except socket.gaierror` Block, der den Fehler nur loggt und *weiterläuft*, statt zu blockieren. Außerdem nutzt der nachfolgende `urllib`-Aufruf intern DNS erneut, was klassisches DNS-Rebinding ermöglicht (Validierung und Fetching nutzen nicht dieselbe IP).

2. Betroffene Stellen
Datei                          Zeile(n)  Rolle
backend/api/db/crud/templates.py 57-61   Hauptort des Bugs (except block für gaierror fail-open)
backend/api/db/crud/templates.py 141-150   Aufrufer (Fetching mit urllib, DNS wird erneut aufgelöst)

3. Code-Snippet (eingebettet)
```python
    try:
        # Resolve hostname to IP
        ip_list = socket.getaddrinfo(hostname, None)
        for ip_info in ip_list:
             ip = ip_info[4][0]
             if is_private_ip(ip):
                 raise HTTPException(status_code=400, detail=f"Access to private IP {ip} is denied.")
    except socket.gaierror:
        # If hostname cannot be resolved, log it and continue or fail?
        # A failed resolution might just be a bad domain, urllib will fail later anyway.
        # BUT fail-open here is dangerous if urllib resolves it differently!
        pass
        #raise HTTPException(status_code=400, detail="Invalid URL: Hostname resolution failed.")
```

4. Erwartetes Verhalten
1. Bei einem DNS-Auflösungsfehler (`socket.gaierror`) darf die Funktion nicht "fail-open" agieren, sondern muss sofort mit einem Fehler abbrechen.
2. Selbst wenn DNS-Auflösung klappt, ist dies durch TOCTOU (Time of Check to Time of Use) via DNS-Rebinding angreifbar. Idealerweise sollte man den Fetch mit der aufgelösten IP und angepasstem Host-Header machen oder einen Rebinding-Schutz verwenden. Das Minimum ist jedoch, das "Fail-Open" bei unresolvable hosts zu schließen.

5. Tatsächliches Verhalten
Wenn ein Hostname bei `validate_url` nicht auflösbar ist (z. B. wegen temporärem DNS-Fehler, oder weil ein Angreifer eine Domain kontrolliert, die beim ersten Mal `gaierror` wirft und beim zweiten Mal durch `urllib` auf `127.0.0.1` auflöst - z.B. custom DNS Server, der zuerst nichts zurückgibt und dann localhost), geht der Code weiter. Auch ohne Rebinding wird ein `gaierror` ignoriert, was schlechter Stil und potenziell gefährlich ist.

6. Reproduktion
Schritt-für-Schritt, ausführbar:
1. Rufe `/api/templates/` (POST) auf mit einer Template URL `http://irgend-eine-dns-rebinding.domain.com/template.json`.
2. Sorge dafür, dass der erste DNS-Request einen Fehler liefert (`gaierror`).
3. Die Validierung rutscht durch den `except socket.gaierror: pass` Block.
4. `urllib` versucht den Fetch. Wenn die Domain nun auf `127.0.0.1` zeigt (Rebinding), wird der Request ans interne System gesendet, und der SSRF-Schutz ist wirkungslos umgangen.

7. Root-Cause-Analyse
Auskommentierter Code im Fehler-Handling (`except socket.gaierror`). Der Entwickler hat `raise HTTPException` auskommentiert und ein `pass` stehen lassen, wodurch bei DNS-Fehlern die Validierung als erfolgreich gilt ("fail-open").

8. Impact
User-Impact: Keiner im Normalfall.
Daten-Impact: SSRF ermöglicht Abfragen des lokalen Netzwerks oder des Docker-Hosts.
Security-Impact: High (Server-Side Request Forgery Bypass).
Performance-Impact: Keiner.

9. Fix-Richtung (kein Code, nur Strategie)
Entferne das `pass` im `except socket.gaierror` Block und wirf stattdessen eine `HTTPException(status_code=400)`. Für perfekten SSRF-Schutz müsste auch das TOCTOU-Problem (DNS-Rebinding) angegangen werden, aber das Fixen des Fail-Opens ist der kritischste erste Schritt.

10. Test-Vorschlag
Mocke `socket.getaddrinfo`, sodass es einen `socket.gaierror` wirft. Rufe `validate_url` auf. Es muss ein `HTTPException(400)` geworfen werden, nicht lautlos durchgehen.

11. Referenzen
Verwandte Funktionen/Module im Repo: backend/api/db/crud/templates.py
Externe Doku falls relevant:

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: SSRF Protection Fail-Open on DNS Resolution Error

Aktueller Code:
```python
    except socket.gaierror:
        # If hostname cannot be resolved, log it and continue or fail?
        # A failed resolution might just be a bad domain, urllib will fail later anyway.
        # BUT fail-open here is dangerous if urllib resolves it differently!
        pass
        #raise HTTPException(status_code=400, detail="Invalid URL: Hostname resolution failed.")
```

Bitte:
1. Implementiere den Fix (Entferne `pass` und aktiviere den `raise` oder eine ähnliche Exception).
2. Schreibe den Regressionstest aus §10 (sofern möglich).
3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
