# Prüfung des eingereichten 117-Punkte-Berichts

Stand: 2026-10-02, lokaler YachtPlus-Arbeitsstand, Version 3.0.1 als unveröffentlichter Prüfkandidat.

Nachprüfung: Der Linux-CI-Lauf des Kandidaten schlug mit den unten ergänzten
Schutzstack-Startfehlern fehl. Die Korrektur wird als Kandidat 3.0.2 geprüft;
die Nachweise für 3.0.1 belegen diesen neuen Stand nicht.

Die Prüfung bezog vorhandene lokale Änderungen ein. Bereits korrigierte
Punkte wurden erneut am aktuellen Code geprüft; zusätzliche Fehler erhielten
Korrekturen und Regressionstests. Die Tabelle beschreibt den resultierenden
Stand und beansprucht keine vollständige Laufzeitprüfung aller Plattformen.

## Ergebnis und Nachweise

Vor der Zusammenführung mit den zwischenzeitlichen Remote-Commits:

- Backend: **852 Tests bestanden**, einschließlich 59 zusätzlicher
  Sicherheits-, Docker-, Compose-, Import- und Migrationsregressionen.
- Frontend: **197 Tests bestanden**, einschließlich sieben neuer Prüfungen
  zu Refresh-Konkurrenz, Zustandsbereinigung, Containeridentität und Datenformaten.
- Release-/Sicherheits-Skripte: **42 Tests bestanden**.
- Produktionsfrontend und Bundle-Grenzen bestanden; npm audit meldete nach
  den kompatiblen Sicherheitsupdates keine bekannten Schwachstellen.
- Alembic: frische, ältere, wiederholte und unterbrochene SQLite-Upgrades
  bestanden. SMTP-Backfill, fehlende optionale SMTP-Tabelle und persistente
  Credential-Versionen sind durch Integrationstests abgedeckt.
- Das vollständig gehashte universelle Test-Lockfile wurde zusätzlich mit
  `pip install --dry-run --require-hashes` validiert.

Der zusammengeführte Stand ist unten mit seinen abschließenden Prüfungen dokumentiert.

## Abgleich der Befunde

| Nr. | Befundgruppe | Resultierender Stand / Nachweis |
|---|---|---|
| 1–5 | Selbst-Rechtevergabe, Setup-Übernahme, 2FA-Rotation, inaktive Konten, API-Key-Scope | Selbst- und Admin-Schemas getrennt; atomarer Setup-Claim und Finalize-Checks; aktives 2FA kann nicht über generate überschrieben werden; aktive Konten und Credential-Version werden zentral geprüft; API-Keys dürfen nur Daten per GET/HEAD lesen und keine Auth-Endpunkte verwenden. HTTP- und WebSocket-Regressionen. |
| 6 | SMTP-Passwort | Nur aktive Administratoren dürfen SMTP verwalten. Antworten enthalten keine Zugangsdaten; Speicherung und bestehende Passwörter werden verschlüsselt. `password=null` erhält das konfigurierte Passwort. |
| 7–10 | CSRF, verändernde GETs, Refresh/Widerruf, Passwortbestätigung | Double-Submit-CSRF mit exakter Origin-Prüfung einschließlich Port; WebSocket-Host/Origin-Prüfung; Mutationen nutzen POST/DELETE; Refresh widerruft den alten JTI; Sicherheitsänderungen rotieren die Kontoversion; DB-Ausfälle erlauben keine Authentifizierung. Passwortänderung verlangt das aktuelle Passwort. |
| 11–13 | Letzter Admin, Lösch-Race, Berechtigungsfelder | Bearbeiten/Löschen schützen den letzten aktiven Admin mit gemeinsamem DB-Schreiblock; eigene Deaktivierung/Degradierung wird abgewiesen; alle vier Berechtigungsfelder einschließlich Restart werden gespeichert. Konkurrenztest mit zwei Admin-Löschungen. |
| 14–17 | Proxy-IP/HTTPS, Geheimnisdateien, Datenbank-Zeitzonen | nginx akzeptiert Weiterleitungsheader nur von explizit vertrauten Proxies; Backend vertraut dem internen nginx. Cookie-Secure wird aus HTTPS/trusted Proto oder expliziter Einstellung ermittelt. Schlüssel/Salt werden vollständig geschrieben, fsynced und atomar veröffentlicht; leere/kurze Dateien brechen den Start ab. Migration korrigiert PostgreSQL-Timestamp-Typen. Live-PostgreSQL bleibt ungeprüft. |
| 18–24 | Lockout, Timing, TOTP-Replay, Key-Löschung, IPv6, DISABLE_AUTH, PBKDF2 | Benutzernamen werden einheitlich normalisiert; Dummy-Bcrypt nutzt Cost 13; TOTP konsumiert den tatsächlich passenden Zähler atomar mit ±1-Fenster; widerrufene Keys können idempotent gelöscht werden; IPv6-Hosts korrekt zerlegt; Auth-Bypass liefert ein TokenData-Objekt; aufwendige Entschlüsselung außerhalb des Event-Loops. |
| 25–26 | Audit-Abdeckung und Setup-Abfragen | Erfolgreiche authentifizierte Mutationen und Login-Versuche werden ohne Request-Bodies protokolliert. Setup-Status besitzt einen kurzen Cache. Audit-Persistenzfehler werden serverseitig protokolliert. |
| 27–32 | Host-Pfade, Edit/Rollback, Geheimnisse in App-/Compose-Antworten, Compose-Inhalte/Umgebung | Normalisierte Mount-/Device-Regeln und Admin-Grenzen; Container-Edit mit erforderlichen Rechten und Rollback; App-/Update-Details erfordern die Operatorberechtigung, normale Compose-Projektlisten enthalten keine Umgebungswerte. Compose-Inhalte validiert und sichere Standardprofile eingesetzt; Subprozesse erhalten nur erlaubte Verbindungs-/Betriebsvariablen. |
| 33–37 | Terminal-Auth, Compose-Rechte/Threadpool, Fehlertexte, Aktionen, Self-Update | Terminal nur mit Cookie und aktiver Session; pull/restart und down/delete korrekt geschützt; Compose-Pool auf zwei Threads begrenzt; Daemon-Details und ungültige HTTP-Statuswerte abgeschirmt; Aktionen explizit zugelassen. Update-Worker verwenden den konfigurierten Proxy und keinen Host-Socket-Mount. |
| 38–40 | SSRF, unbeschränkte Fetches/YAML, SMTP-Verbindung | DNS-Adressen einmal sicher aufgelöst und beim Socket-Aufbau verwendet; CGNAT/NAT64/interne Ziele gesperrt; Größen-, Zeit- und YAML-Komplexitätsgrenzen. SMTP-Zertifikats-/Hostname-Prüfung, Timeout und SMTPS 465; Alerts außerhalb des Login-Pfads und begrenzt. |
| 41–43 | SPA-Header, Proxy-Aussagen, Compose-Beispiel | nginx liefert CSP, X-Frame-Options und weitere Header auch für die SPA. Proxy-Dokumentation beschreibt tatsächliche Grenzen; Versions-/Ping-Freigaben und Image-/Start-Konfiguration korrigiert. Linux-Deploymentprüfung erfolgt erst in CI. |
| 44–49 | aiodocker Exec/Logs, Deploy-Netzwerk, Ressourcen, Prune, Unused | API-Verträge von aiodocker 0.25 verwendet; Terminal-Resize separat, Disconnect beendet Streamaufgaben; Logs begrenzt; konfliktfreie Netzwerkparameter; Objekt-APIs für Volumes/Netzwerke und echte Prune-API; Containerobjekte korrekt ausgewertet. Backend-Regressionstests mit Docker-Mocks. |
| 50–53 | Templates: Async-Loading, Portainer v2, Refresh, Import | Beziehungen auch beim Edit eager geladen; Portainer-v2-Wrapper und String-Commands unterstützt; Ports/Typ/Fehlerbehandlung korrigiert; Import vollständig vor Änderungen validiert, unbekannte Felder gefiltert und Fremd-IDs verworfen. Leere Pflichtfelder werden mit 422 abgewiesen. |
| 54–58 | Scheduler, Watchtower-Ergebnis, Update-Fehler, Self-Erkennung | Compose-Auto-Update standardmäßig aus, explizites Opt-in; Leader-Lock; Projektname validiert und Aktionsergebnis abgewartet; Worker-Exit/Timeout/Rollback überprüft. cgroup-v2 unterstützt über immutable Docker-HOSTNAME; Self-Restart nutzt einen eigenen Client nach dem Request. Reales Self-Update noch nicht ausgeführt. |
| 59–61 | Kaputte Compose-Dateien, Dateisuche, Projektlöschung | Listen überspringen ungültige Top-Level-/Resource-Mappings; unterstützte Dateinamen mit fester Priorität, keine rekursive Symlink-Suche. Validierter normalisierter Inhalt wird atomar in die ausgewählte Datei geschrieben; CLI verwendet diese explizit. Symlinks werden abgewiesen. Löschung führt zuerst down aus und erhält Dateien bei Fehlschlag. |
| 62–67 | Gestoppte Logs, Speicher/CPU, Stats-Route, Blocking-Logs, Env-Konvertierung | Gestoppte Container liefern historische Logs und ein SSE-Endereignis; UI schließt Streams. Inactive Page-Cache abgezogen; unvollständige CPU-Frames toleriert; Stats-Route vorhanden und aiodocker-Listen-Snapshots verarbeitet; sync Logs im Thread; nullable Env-Defaults behandelt. |
| 68–70 | Image-Helper, Cache, Registry-URLs, GHCR | Token-Scope ohne Tag; ungenutzter Image-Inspektionshelper bleibt als getesteter Kompatibilitätscode. Registry-Cache begrenzt; Suchwerte URL-kodiert; öffentliche GHCR-Tags über OCI-Bearer-Token. `date-fns` bleibt für den Chart-Zeitadapter erforderlich. |
| 71–74 | Global-/Worker-Limits, Migrationen, Retention | SlowAPI-Middleware und Default-Limit aktiv; veröffentlichtes Image nutzt einen asynchronen Worker, sodass Memory-Limits nicht vervielfacht werden. Externes Limiter-Backend konfigurierbar. Alembic-Versionen/Upgradepfad vorhanden; stündliche Aufbewahrungsbereinigung mit 90/30 Tagen. |
| 75–83 | Vue-Routen, Vuetify-Display/Activator, URLs, SMTP, Dashboard, Compose-Aktionen, Formulare | Vue-3-Routen und Vuetify-3-Controls; korrekte API-Präfixe/SMTP-Adresse; Stats und korrekte Dashboard-HTTP-Methoden mit Löschbestätigung; kill/rm zugelassen und geschützt; vee-validate-Komponenten und Deploy-Feldbindungen/Stepper migriert. Frontendtests und Produktionsbuild. |
| 84–88 | Refresh, F5-Session, Terminal-UI, Zeilenklick, Container-Duplikate | Gemeinsamer Refresh auch für parallele Store-/Interceptor-Aufrufe mit Fehlerweitergabe und Timeout; Cookie-Session bei Reload überprüft; Terminal-Auswahl/Resize/Benachrichtigungen korrigiert; Vuetify-Zeilenereignisse korrekt verarbeitet; Container über echte ID oder vorhandenen Namen zugeordnet. |
| 89–98 | Theme, Snackbar, Suche, Self-Update-UI, Passwort, Logout, Labels, Datum, Compose-Status, Charts | Theme-Refs im Options-API korrekt und Farben sofort aktualisiert; Snackbar beschreibbar; Suche migriert; Update-Fehler melden nicht ab; normales Username-Format und aktuelles Passwort; komplette Store-Bereinigung; historische Portlabels; Unix-Sekunden; Compose-v1/v2/Labels; Chart-Prop passend. |
| 99–101 | AuthDisabled, weitere Vuetify-Reste, kleinere UI-/Logfehler | Getter vorhanden; Komponenten/Slots/Props und Tabellenüberschriften migriert; Manifest-404 entfernt; Logs begrenzt und Download-URLs freigegeben. Veraltete, nachweislich unreferenzierte Komponenten entfernt. |
| 102–106 | Socket-Gruppen, nginx, Prozessführung, Logging, fail2ban | Unterstütztes geschütztes Deployment verwendet TCP-Proxy statt direkter Host-Socket-Anbindung. Upload-Limit 8 MiB, stdout-Logs, Terminal-Timeout 1 h; loopback Gunicorn, supervision beider Prozesse, kein Start-chown; INFO-Logging. fail2ban mit persistenten Anwendungssperren und fail-closed Zustandsüberwachung. Linux-Laufzeitnachweis offen. |
| 107 | CI | Tests, Build-, Migrations- und Sicherheits-Gates; Actions auf verifizierte SHAs gepinnt; Publisher auf vertrauenswürdige erfolgreiche Runs beschränkt. **Offen: Multiarch-Publikation**, aktuell amd64. Ruff bleibt ausdrücklich informativ; kein erfolgreicher CI-Run wird hier vorweggenommen. |
| 108–110 | Image, Ignore-Regeln, Requirements | Multi-Stage-Image, echter Docker-CLI, Compose-Prüfsumme, Node 22, Healthcheck und verbindliches npm ci. Venv/DB/Tests/Geheimnisse ausgeschlossen. Runtime-/Dev-Python-Locks mit Hashes, Testpakete getrennt, lokale Requirements und DB-URL-Konvertierung korrigiert. Reales Image noch nicht gebaut. |
| 111 | Frontend-Abhängigkeiten / tote Dateien | Ungenutzte brace/core-js/service-worker/virtual-scroller/webfontloader-Pakete entfernt; lokale Fonts und @xterm-Nachfolger; Vuetify-Tree-Shaking. `date-fns` und Day.js haben unterschiedliche tatsächlich genutzte Aufgaben. Veraltete unreferenzierte Komponenten/Plugins entfernt. |
| 112–116 | Architektur-, Auth-, Sicherheits- und Env-Dokumentation | AGENTS/README beschreiben Vuex, korrekte Middleware-Reihenfolge, Cookie-/CSRF-/Key-Regeln, tatsächliche Defaults und unterstützte Konfiguration. ENV_FILE ist als nicht unterstütztes Legacy-Konzept gekennzeichnet. |
| 117 | Alte Audits / Testzahlen | Historische Berichte als historisch gekennzeichnet; falsche Pinia-/Bcrypt-Key-/Persistenzaussagen berichtigt. Aktuelle Testzahlen und Migrationen hier sowie im Changelog dokumentiert. |

## Upgrade und Grenzen

Vor einem produktiven Upgrade Datenbank, `.secret_key` und `.fernet_salt`
gemeinsam sichern. Das Image führt Alembic vor dem API-Start aus. Bereits
existierende Tokens ohne `av` werden verworfen; Benutzer müssen sich neu
anmelden und API-Keys neu erstellen. Sicherheitsrelevante Kontoänderungen
widerrufen außerdem alle zugehörigen Sessions/Keys.

SMTP-Passwörter werden nicht zurückgesendet. Ein leeres oder `null`-Passwort
behält die bisherige Konfiguration. TOTP-Codes können nach dem einmaligen Verbrauch auch
für eine andere Aktion im selben Zeitfenster nicht wiederverwendet werden.
Compose-Auto-Updates laufen nur mit `COMPOSE_AUTO_UPDATE=true`.

Kein Live-Nachweis für Linux Docker, reale Container-Rollbacks, PostgreSQL,
MySQL oder externe Mail-/Registrydienste auf diesem Windows-Rechner. Die
Backendtests verwenden isolierte Datenbanken und Docker-/SMTP-Mocks. Der
Browsercheck verwendet isoliertes Chrome und kontrollierte API-Antworten.
Diese Prüfungen ersetzen keinen produktiven Deploymenttest; die konfigurierte
CI enthält die Linux-Image- und Schutzstack-Gates.

## Abschließender zusammengeführter Stand

Die acht neueren Commits von `origin/audit-fix-2026-08-21` wurden integriert.
Zusätzliche Remote-Korrekturen für Rollbacks, Passwortlängen, Template-Fehler,
WebSocket-Validierung, Registry-Anfragen, Portlinks und UI-Ladezustände wurden
erhalten. Der Merge schützt weiterhin alle neu eingeführten Sicherheitsverträge.

- **860 Backend-Tests bestanden.**
- **217 Frontend-Tests bestanden.**
- **42 Release-/Sicherheits-Skriptprüfungen bestanden.**
- Produktionsbuild und Bundle-Grenzen bestanden; `dist/version.json` enthält
  exakt `3.0.1`.
- Eingangs-JavaScript: 256.927 Bytes, vollständiges anfängliches JavaScript:
  490.153 Bytes, anfängliches CSS: 658.530 Bytes.
- Browserprüfung: isolierter Chrome mit kontrollierten API-Antworten;
  **11 Prüfungen bestanden**, keine JavaScript-Laufzeitfehler. Login/Dashboard,
  POST-Lifecycle-Aktion, Containerliste/Spalten/Aktionen, Compose-Steuerung,
  Settings-Deep-Link, Theme nach Reload und mobile Navigation geprüft.
  Tatsächliche Vue-Seiten und Steuerelemente, kein Live-Docker-Nachweis.

Publikationsziel ist der bestehende Branch `audit-fix-2026-08-21`. Dieser
Prüfkandidat beansprucht weiterhin keine verifizierte Linux-/Multiarch-Version.

## CI-Nachprüfung und Kandidat 3.0.2 (Run R-023)

Der CI-Lauf [36979071014](https://github.com/xNicolas99/YachtPlus/actions/runs/36979071014)
für `3adb5ab` zeigte zwei reale Startfehler des geschützten Linux-Stacks:

- Fail2ban 1.0.2 startet Aktionen mit `umask 077`. Dadurch wurde `bans` trotz
  `mkdir(mode=0755)` tatsächlich mit `0700` erzeugt. Der Guard UID 1001 war
  gesund, aber die App UID 1000 konnte den Zustand in ihrem RO-Mount nicht
  lesen und antwortete mit protection-unavailable 503. Die Startaktion setzt
  den Modus nun ausdrücklich auf `0755` und repariert bestehende Volumes.
- Der Docker-Socket-Proxy konnte auf seinem schreibgeschützten Root-Dateisystem
  `/run/haproxy.pid` nicht schreiben. Beide Compose-Dateien geben ihm dafür
  ein begrenztes `/run`-tmpfs; das Root-Dateisystem bleibt schreibgeschützt.

Kandidat `3.0.2` ergänzt gezielte Regressions-/Smoke-Prüfungen für diese
Verträge sowie Startdiagnosen zu Health, UID/GID und Dateimodi ohne Ausgabe
der Container-Umgebung. Lokal bestanden 860 Backend- und 217 Frontend-Tests,
Produktionsbuild/Bundle-Grenzen und ein frisches SQLite-Alembic-Upgrade.
`dist/version.json` enthält exakt `3.0.2`. Die Skriptsuite führte 44 Prüfungen
aus: 43 bestanden, eine POSIX-Rechte-/umask-Prüfung wurde auf Windows
ausdrücklich übersprungen. Der unten verlinkte Linux-CI-Lauf führte alle
44 Prüfungen erfolgreich aus. Logs: `report/audit-ci-backend-r023.txt`,
`report/audit-ci-migration-r023.txt`, `report/audit-ci-script-r023.txt`.

Der erste Linux-Nachweis liegt auf `ac869d7` vor:
[PR-CI 37009114081](https://github.com/xNicolas99/YachtPlus/actions/runs/37009114081)
und [Push-CI 37009077607](https://github.com/xNicolas99/YachtPlus/actions/runs/37009077607)
bestanden Image-Build, Inhalts-/Startprüfungen, Migrationen und alle 44
Skriptprüfungen. Der echte fail2ban-Stack bestand Ban/Unban, persistente Bans
und Ausfall/Wiederherstellung der Pflichtprotection. Diese Linux-Nachweise
ergänzen die früheren lokalen Mock-/Browserprüfungen.
Das PR-Image `yachtplus:ci-smoke` hatte die Docker-Image-ID
`sha256:aa5fee1f0e53600f37cb48f2ac3a43d783326a0e97a543fe561495441a24efae`.
Das bezeichnet das lokal im CI gebaute Image, keinen veröffentlichten
Registry-Manifest-Digest; eine nicht belegte Imagegröße wird hier nicht genannt.

## CodeQL-Nachkorrektur innerhalb von 3.0.2 (Run R-024)

Die [CodeQL-Analyse 37009114025](https://github.com/xNicolas99/YachtPlus/actions/runs/37009114025)
hat erfolgreiche Python-/JavaScript-Analyze-Jobs; der separate Results-Check
`110844629671` scheiterte dagegen mit drei High-Befunden. Dieser Unterschied
blockiert den Merge trotz des erfolgreich gelaufenen Schutzstacks.

Die Nachkorrektur ersetzt die GHCR-Repositoryprüfung mit ReDoS-anfälliger
Regex durch einen linearen Parser und die zwei gemeldeten URL-Testfixtures
durch exakte Host-/Pfad-/Titelvergleiche. GHCR-Referenzen sind vor
URL-Parsing auf 1024 Zeichen, Repositorynamen auf 255 Zeichen begrenzt;
gültige Segmente verwenden ausschließlich die zugelassene ASCII-Menge.
Ungültiger Input löst keine HTTP-Anfrage aus. Es bleibt dieselbe Lieferung
`3.0.2`. Die finale lokale Backend-Vollsuite bestand **884 Tests**, darunter
24 zusätzliche Regressionen; Log `report/audit-ci-backend-r024-final.txt`.
Die unveränderten **217 Frontend-Tests**, Produktionsbuild/Bundle-Grenzen und
frische SQLite-Migration sind für Version `3.0.2` ebenfalls bestanden.
Ein frischer erfolgreicher CodeQL-Results-Check und die erforderlichen CI-Jobs
für den zuletzt korrigierten tatsächlichen HEAD stehen noch aus.

Ein Merge nach `master` oder eine Veröffentlichung wird weiterhin nicht
behauptet. Alle erforderlichen Checks müssen auf dem tatsächlichen letzten
Kandidaten-Commit erfolgreich sein; der grüne Lauf auf `ac869d7` bestätigt
keine nachfolgenden Änderungen.
