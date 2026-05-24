# BUG-001: Global 400 Bad Request due to TrustedHostMiddleware rejecting Host Header

- **Severity:** High
- **Kategorie:** Middleware
- **Confidence:** High
- **Sweep-Quelle:** A1, A2, A3.1, A4, A5
- **Erstmals erkannt in:** Live-Test gegen `/api/setup/status`
- **Related Bugs:** none

## 1. Zusammenfassung
Alle Endpunkte geben einen `400 Bad Request` zurück, sobald die App nicht über `localhost` oder `127.0.0.1` aufgerufen wird (z. B. im Container über Nginx mit der echten Host-IP). Dies liegt an der `TrustedHostMiddleware`, die den weitergeleiteten Host-Header blockiert, da er nicht in der stark eingeschränkten `ALLOWED_HOSTS`-Konfiguration enthalten ist.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|---|---|---|
| `backend/api/main.py` | 59 | Registrierung der `TrustedHostMiddleware` |
| `backend/api/settings.py` | 38 | Definition des `ALLOWED_HOSTS` Defaults |

## 3. Code-Snippet
```python
# backend/api/settings.py:38
    # Networking
    ALLOWED_HOSTS: list = os.getenv("YACHT_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if os.getenv("YACHT_ALLOWED_HOSTS") else ["localhost", "127.0.0.1", "[::1]"]

# backend/api/main.py:58-61
# Reject requests with Host headers that aren't in ALLOWED_HOSTS so the API
# can't be tricked into emitting absolute URLs (password resets etc.) under
# an attacker-controlled host.
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=get_settings().ALLOWED_HOSTS,
)
```

## 4. Erwartetes Verhalten
Bei einem Aufruf der API über eine beliebige (oder vom Proxy gesetzte) IP/Host (z.B. `10.10.10.100`) soll der Request normal verarbeitet werden und, je nach Endpunkt und Auth-Status, einen 2xx, 401 oder 403, aber nicht global 400 liefern.

## 5. Tatsächliches Verhalten
```
HTTP/1.1 400 Bad Request
date: Sun, 24 May 2026 12:32:29 GMT
server: uvicorn
content-length: 19
content-type: text/plain; charset=utf-8

Invalid host header
```

## 6. Reproduktion
```bash
curl -i -H "Host: 10.10.10.100" http://localhost:8000/api/setup/status
```

## 7. Root-Cause-Analyse
Die Nginx-Reverse-Proxy-Konfiguration in `nginx.conf` reicht korrekterweise den externen Host-Header des Clients an Gunicorn weiter (`proxy_set_header Host $host;`). Gunicorn bzw. Uvicorn übergibt diesen an FastAPI. Die `TrustedHostMiddleware` prüft nun, ob der Wert in `ALLOWED_HOSTS` steht. Da der Default in `settings.py` nur `localhost`, `127.0.0.1` und `[::1]` zulässt, wird jeder externe Request hart mit einem `400 Bad Request` ("Invalid host header") abgewiesen.

## 8. Impact
- User / Daten / Security / Performance: Kompletter Ausfall der Anwendung (High), da weder Setup noch Login noch andere Aufrufe möglich sind, sobald die App auf einem dedizierten Host / über IP aufgerufen wird und `YACHT_ALLOWED_HOSTS` nicht exakt gesetzt ist. Es kommt jedoch nicht zu Datenverlust oder Auth-Bypass.

## 9. Fix-Richtung
Den Standardwert für `ALLOWED_HOSTS` in `backend/api/settings.py` auf `["*"]` setzen, sodass im Container/Reverse-Proxy-Betrieb standardmäßig alle Hosts erlaubt sind (ähnlich wie es oft bei Dockerisierten FastAPI-Apps gemacht wird). Alternativ eine ausführlichere Dokumentation für `YACHT_ALLOWED_HOSTS` hinzufügen, was aber die Out-of-the-Box Experience bricht.

## 10. Test-Vorschlag
Ein Request mit dem Header `Host: yachtplus.local` oder einer Dummy-IP auf `/api/setup/status` muss einen anderen Status als 400 (z. B. 200 oder 428) zurückgeben.

## 11. Referenzen
FastAPI/Starlette `TrustedHostMiddleware` Docs.

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier.
>
> **Bug:** Global 400 Bad Request due to TrustedHostMiddleware rejecting Host Header
> **Datei(en):** backend/api/settings.py, backend/api/main.py
> **Aktuelles Verhalten:** HTTP 400 "Invalid host header" bei Requests mit externen Hosts
> **Erwartetes Verhalten:** Requests werden vom Router verarbeitet.
> **Root Cause:** ALLOWED_HOSTS default ist zu restriktiv für Docker/Nginx setup.
> **Vorgeschlagene Fix-Richtung:** ALLOWED_HOSTS Default auf `["*"]` ändern.
> **Testfall der danach passen muss:** `curl -H "Host: 10.10.10.100" http://127.0.0.1:8000/api/setup/status`
>
> Aktueller Code:
> ```python
> ALLOWED_HOSTS: list = os.getenv("YACHT_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if os.getenv("YACHT_ALLOWED_HOSTS") else ["localhost", "127.0.0.1", "[::1]"]
> ```
>
> Bitte:
> 1. Minimalen Fix implementieren.
> 2. Regressionstest schreiben.
> 3. Begründen warum dein Fix den Root Cause behebt.
> 4. Risiken/Seiteneffekte auflisten.
