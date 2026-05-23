# BUG-005

Severity: Low
Kategorie: Config
Confidence: High (statisch erkannt)
Erstmals erkannt in: docs/APACHE_REVERSE_PROXY.md
Related Bugs: none

1. Zusammenfassung (2–3 Sätze)
In `docs/APACHE_REVERSE_PROXY.md` wird in einem Beispiel vorgeschlagen, WebSockets über das unverschlüsselte `ws://`-Protokoll weiterzuleiten (`ws://`). In einer produktiven, mit HTTPS gesicherten Umgebung sollte intern und extern sichergestellt sein, dass das Protokoll sicher ist oder die Anleitung zumindest auf die Risiken von unverschlüsseltem `ws://` aufmerksam macht, besonders wenn sich der Proxy auf einem anderen Rechner befindet. Da es sich nur um eine Dokumentation handelt, ist der Schweregrad gering.

2. Betroffene Stellen
Datei: docs/APACHE_REVERSE_PROXY.md
Zeilen: 55
Rolle: Dokumentation

3. Code-Snippet
```markdown
1.  **RewriteRule for WebSockets**: explicitly checks for `Upgrade: websocket` header and
proxies via `ws://`.
```

4. Erwartetes Verhalten
Dokumentationen sollten Best Practices wie `wss://` für produktive Konfigurationen (sofern anwendbar) nutzen oder klarstellen, dass `ws://` nur in isolierten lokalen Netzwerken genutzt werden sollte.

5. Tatsächliches Verhalten
Empfiehlt indirekt oder dokumentiert `ws://`.

6. Reproduktion
Schritt-für-Schritt:
Lies `docs/APACHE_REVERSE_PROXY.md`.

7. Root-Cause-Analyse
Doku-Drift / Mangelnde Sicherheitskontexte in Beispiel-Konfigurationen.

8. Impact
User-Impact: Admins kopieren möglicherweise unsichere Konfigurationen.
Daten-Impact: keiner
Security-Impact: Schwache Security-Posture durch unsicheres Beispiel.
Performance-Impact: keiner

9. Fix-Richtung
Aktualisiere das Dokument, um auf `wss://` als Best Practice hinzuweisen oder erkläre, dass `ws://` nur für lokales Loopback (z. B. Proxy auf demselben Host wie die App) sicher ist.

10. Test-Vorschlag
Nicht auf Codeebene testbar. Doku Review.

11. Referenzen
Verwandte Funktionen: `docs/APACHE_REVERSE_PROXY.md`

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: Dokumentation referenziert unsicheres ws:// anstatt wss:// oder fehlenden Kontext.

Aktueller Code:
```markdown
1.  **RewriteRule for WebSockets**: explicitly checks for `Upgrade: websocket` header and proxies via `ws://`.
```

Bitte:
1. Implementiere den Fix mit minimaler Änderung. Ergänze einen Satz über die Nutzung in lokalen Netzwerken vs. HTTPS-Terminierung.
2. Erkläre kurz, warum dein Fix den Root Cause behebt.
3. Liste Seiteneffekte/Risiken auf.
