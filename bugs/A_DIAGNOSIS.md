# A1. Reproduktion
Test mit Nginx: `curl -i -H "Host: 10.10.10.100" http://127.0.0.1:8000/api/setup/status` -> 400 Bad Request
Test ohne Nginx (Gunicorn direkt): `curl -i -H "Host: 10.10.10.100" http://localhost:8000/api/setup/status` -> 400 Bad Request

Ergebnis: Der 400 Fehler liegt in der FastAPI Middleware oder Gunicorn-Config.

# A2. Middleware-Stack-Inventar
In `backend/api/main.py`:
FastAPI führt Middlewares in umgekehrter Reihenfolge der Registrierung aus:
1. `add_security_headers` (Zuletzt hinzugefügt mit `@app.middleware("http")`) - main.py:64 - Fügt CSP Header hinzu - Gibt keinen 400 zurück.
2. `TrustedHostMiddleware` - main.py:59 - Prüft Host-Header gegen `ALLOWED_HOSTS` - Ja (400 wenn nicht in allowed_hosts).
3. `CORSMiddleware` - main.py:50 - Prüft Origin - Selten 400, eher 403.
4. `check_setup_status` (Zuerst hinzugefügt mit `@app.middleware("http")`) - main.py:20 - Prüft ob Setup completed - Gibt 428 zurück.

# A3. Hypothesen-Tests
## A3.1 — TrustedHostMiddleware
Test: `curl -i -H "Host: 10.10.10.100" http://127.0.0.1:8000/api/setup/status` liefert 400 Bad Request, Body: `Invalid host header`.
In `backend/api/settings.py` ist `ALLOWED_HOSTS` defaultmäßig `["localhost", "127.0.0.1", "[::1]"]`.
Der Host-Header der Nginx weitergibt ist `10.10.10.100` (die IP des Hosts).
Da die Host IP nicht in `ALLOWED_HOSTS` ist, lehnt `TrustedHostMiddleware` die Anfrage mit 400 ab.

## A3.2 — forwarded_allow_ips
Nicht der primäre Grund, da die direkte Verbindung auch 400 liefert.

## A3.3 — Custom Middlewares
Kein Setup Guard Problem für diesen Endpunkt, da wir direkt den Host-Header Fehler erhalten.

## A3.4 — Nginx ↔ Gunicorn Header-Mismatch
Nginx setzt `proxy_set_header Host $host;`. Wenn der Client `10.10.10.100` als Host angibt, gibt Nginx das an Gunicorn/FastAPI weiter, was von `TrustedHostMiddleware` abgelehnt wird.

## A3.5 — CORS
Wurde nicht getroffen, da `TrustedHostMiddleware` davor feuert.

## A3.6 — Pydantic-Validation
Wurde nicht getroffen.

# A4. Response-Body inspizieren
Body bei `curl -i -H "Host: 10.10.10.100" http://127.0.0.1:8000/api/setup/status`:
`Invalid host header`

# A5. Root Cause
- **Welche Hypothese ist bestätigt?** Hypothese 1: `TrustedHostMiddleware` rejected `Host`-Header.
- **Welche Datei:Zeile ist die Quelle?** `backend/api/main.py:59` (`app.add_middleware(TrustedHostMiddleware, allowed_hosts=get_settings().ALLOWED_HOSTS)`) und `backend/api/settings.py:38` (wo `ALLOWED_HOSTS` default gesetzt wird).
- **Was genau geht schief?** Die `TrustedHostMiddleware` von Starlette prüft den `Host`-Header gegen die Liste `ALLOWED_HOSTS`. Standardmäßig enthält diese Liste nur `localhost`, `127.0.0.1`, und `[::1]`. Wenn die App über Nginx angesprochen wird, leitet Nginx den externen Hostnamen oder die IP des Servers (z.B. `10.10.10.100`) im `Host`-Header an FastAPI weiter. Da dieser nicht in der Default-Liste steht, lehnt die Middleware alle Requests (sogar parameterlose GETs) mit einem `400 Bad Request` ("Invalid host header") ab, bevor der Request überhaupt zum Router gelangt.
- **Was ist die kleinstmögliche Fix-Richtung?** Entweder die Default-Werte für `ALLOWED_HOSTS` so anpassen, dass sie eine Wildcard `*` enthalten (oder zumindest in Umgebungen ohne explizit gesetzten Host flexibler sind), oder in der Dokumentation/Setup zwingend eine Konfiguration von `YACHT_ALLOWED_HOSTS` vorschreiben. Eine einfache Lösung für Docker-Setups ist, `"*"` als Default für `ALLOWED_HOSTS` zu erlauben.
- **Welche Konfig/ENV/Header muss anders sein?** `ALLOWED_HOSTS` (Umgebungsvariable `YACHT_ALLOWED_HOSTS`) muss entweder die IP/den Hostnamen enthalten, über die/den die App aufgerufen wird, oder auf `*` gesetzt werden.
