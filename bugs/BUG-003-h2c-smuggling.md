# BUG-003

Severity: High
Kategorie: Other
Confidence: Medium (statisch erkannt)
Erstmals erkannt in: nginx.conf
Related Bugs: none

1. Zusammenfassung (2–3 Sätze)
Die Nginx-Konfiguration leitet `Upgrade`- und `Connection`-Header ausnahmslos weiter, was für WebSockets benötigt wird. Wenn diese Weiterleitung jedoch nicht auf `Upgrade: websocket` beschränkt wird, ist der Server anfällig für HTTP/2 Cleartext (h2c) Smuggling. Ein Angreifer kann dadurch eine unbeschränkte, langlebige HTTP-Verbindung zum Backend aufbauen und möglicherweise Access-Controls im Reverse-Proxy umgehen.

2. Betroffene Stellen
Datei: nginx.conf
Zeilen: 50, 85
Rolle: Reverse Proxy Konfiguration

3. Code-Snippet
```nginx
            proxy_http_version 1.1;

            # Upgrade Logic for WebSockets and SSE
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;
```

4. Erwartetes Verhalten
Die Upgrade-Header sollten nur dann gesetzt werden, wenn es sich nachweislich um WebSockets (`websocket`) handelt.

5. Tatsächliches Verhalten
Jeder `Upgrade`-Header (einschließlich `h2c`) wird ungeprüft durchgereicht.

6. Reproduktion
Schritt-für-Schritt:
Eine h2c-Smuggling-Anfrage an den Nginx-Server senden (z. B. mit `h2csmuggler`). Wenn das Backend `h2c` Upgrades erlaubt (wie manche Python ASGI-Server), kann eine Tunnelverbindung etabliert werden.
Da FastAPI/Uvicorn standardmäßig kein `h2c` aktiviert (außer explizit konfiguriert), könnte die Ausnutzbarkeit in der Praxis eingeschränkt sein, aber Nginx ermöglicht es.

7. Root-Cause-Analyse
Fehlende Filterung des `$http_upgrade`-Wertes in der Nginx-Konfiguration.

8. Impact
User-Impact: keiner
Daten-Impact: keiner
Security-Impact: Potenzieller Bypass von Nginx-Zugriffskontrollen und direktes Tunneling zum Backend.
Performance-Impact: keiner

9. Fix-Richtung
Füge in der `nginx.conf` eine Überprüfung ein, die `$http_upgrade` nur auf `websocket` setzt, falls `$http_upgrade` den Wert `websocket` enthält, und ansonsten leer lässt oder `close` setzt.

10. Test-Vorschlag
Versuche einen HTTP/1.1 Request mit `Upgrade: h2c` an Nginx zu senden. Nginx sollte den Upgrade-Header nicht ans Backend weiterleiten.

11. Referenzen
Verwandte Funktionen: `nginx.conf` (Location-Blöcke)

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: Nginx H2C Smuggling

Aktueller Code:
```nginx
            proxy_http_version 1.1;

            # Upgrade Logic for WebSockets and SSE
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;
```

Bitte:
1. Implementiere den Fix mit minimaler Änderung. Nutze eine Map-Direktive in nginx.conf, um sicherzustellen, dass nur `websocket` als Upgrade erlaubt wird.
2. Schreibe den Regressionstest (oder passe die Nginx-Conf entsprechend an und erkläre ihn).
3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
