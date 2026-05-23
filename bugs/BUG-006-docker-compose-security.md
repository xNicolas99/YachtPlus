# BUG-006

Severity: Medium
Kategorie: Config
Confidence: High (statisch erkannt)
Erstmals erkannt in: docker-compose.yml
Related Bugs: none

1. Zusammenfassung (2–3 Sätze)
Die ausgelieferte `docker-compose.yml` (sowie die `.example.yml`) startet die Container ohne das Security-Opt-Flag `no-new-privileges:true`. Zudem laufen die Container mit einem beschreibbaren Root-Dateisystem. Dadurch kann ein potenzieller Angreifer, der eine RCE (Remote Code Execution) im Container ausnutzt, sein Privileg über Setuid-Binaries eskalieren und das Dateisystem manipulieren, um bösartige Payloads dauerhaft abzulegen.

2. Betroffene Stellen
Datei: docker-compose.yml und docker-compose.example.yml
Zeilen: 3 (dockerproxy) und 18 (yachtplus)
Rolle: Deployment-Konfiguration

3. Code-Snippet
```yaml
  dockerproxy:
    image: tecnativa/docker-socket-proxy
...
  yachtplus:
    build: .
```

4. Erwartetes Verhalten
Produktiv einsetzbare Container-Deployments sollten `security_opt: ["no-new-privileges:true"]` verwenden und idealerweise mit einem Read-Only-Filesystem (`read_only: true`) plus temporären Laufwerken (`tmpfs`) für Schreibvorgänge laufen.

5. Tatsächliches Verhalten
Diese Absicherungen fehlen, was das System für Nach-Exploitation-Schritte verwundbarer macht.

6. Reproduktion
Schritt-für-Schritt:
Inspeziere `docker-compose.yml`.

7. Root-Cause-Analyse
Security Best Practices für Docker Compose nicht vollständig umgesetzt.

8. Impact
User-Impact: keiner direkt
Daten-Impact: keiner
Security-Impact: Schwache Defense-in-Depth. Im Falle eines Exploits kann der Angreifer tiefer ins System vordringen.
Performance-Impact: keiner

9. Fix-Richtung
Füge `security_opt: ["no-new-privileges:true"]` zu beiden Diensten hinzu. Evaluierung, ob `read_only: true` mit den Anforderungen von YachtPlus harmoniert (es erfordert wahrscheinlich Mounts für SQLite, Logs und Cache-Ordner), andernfalls belasse es bei `no-new-privileges`.

10. Test-Vorschlag
Manuelle Verifikation, dass die Anwendung mit diesen Flags weiterhin erfolgreich bootet.

11. Referenzen
Verwandte Dateien: `docker-compose.yml`, `docker-compose.example.yml`

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: Fehlende Sicherheits-Flags in docker-compose.yml.

Aktueller Code:
```yaml
  yachtplus:
    build: .
    ports:
...
```

Bitte:
1. Implementiere den Fix mit minimaler Änderung. Füge `security_opt: ["no-new-privileges:true"]` bei beiden Services in `docker-compose.yml` und `docker-compose.example.yml` hinzu.
2. Erkläre kurz, warum dein Fix den Root Cause behebt.
3. Liste Seiteneffekte/Risiken auf.
