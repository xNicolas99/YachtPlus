BUG-006

Severity: Medium
Kategorie: Auth
Confidence: High
Erstmals erkannt in: backend/api/utils/security.py
Related Bugs: none

1. Zusammenfassung (2–3 Sätze)
Die Funktion `_resolve_client_ip` ermittelt die Client-IP und vertraut dabei Blindlings dem `X-Real-IP`-Header, solange die direkte Peer-IP als privat gilt (`is_private_ip`). Wenn die Anwendung hinter einem Reverse-Proxy betrieben wird, aber ein Angreifer direkten Zugriff auf den Port des Backends hat (oder der Proxy `X-Real-IP` nicht filtert/überschreibt), kann ein Angreifer eine beliebige private IP in `X-Real-IP` oder `X-Forwarded-For` spoofen und so die IP-Einschränkung in `check_ip_restriction` (die nur Zugriffe von privaten IPs zulässt) umgehen oder Rate Limits fälschen. Das Problem wird dadurch verschärft, dass FastAPI/Uvicorn standardmäßig keine Validierung von `ProxyHeadersMiddleware` durchführt, wenn nicht explizit konfiguriert.

2. Betroffene Stellen
Datei                          Zeile(n)  Rolle
backend/api/utils/security.py 69-71    Hauptort des Bugs (X-Real-IP Vertrauen)

3. Code-Snippet (eingebettet)
```python
def _resolve_client_ip(request: Request) -> str:
    client_ip = request.client.host
    if not client_ip or not is_private_ip(client_ip):
        return client_ip

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
```

4. Erwartetes Verhalten
Man sollte Headern wie `X-Real-IP` oder `X-Forwarded-For` nur vertrauen, wenn der Request von einer **bekannten, vertrauenswürdigen Proxy-IP** kommt (nicht einfach nur von *irgendeiner* privaten IP).

5. Tatsächliches Verhalten
Wenn das Backend im Docker-Netzwerk auf `0.0.0.0:8000` lauscht und ein Angreifer (z. B. aus dem LAN, was eine private IP ist, oder über eine Lücke im Nginx-Setup) direkt auf Port 8000 zugreift, gilt seine IP als privat (`is_private_ip(client_ip)` ist wahr). Dann kann er `X-Real-IP: 192.168.1.100` mitsenden. Der Server nutzt diese IP fürs Rate Limiting (Fail2Ban). Der Angreifer kann so das Rate Limiting auf fremde IPs lenken oder sein eigenes umgehen, indem er bei jedem Login-Versuch eine neue IP im Header sendet.

6. Reproduktion
Schritt-für-Schritt, ausführbar:
1. Greife auf das API direkt zu (falls Port exposed) oder nutze einen Proxy, der `X-Real-IP` des Clients übernimmt statt überschreibt. (Sagen wir, du bist im LAN und greifst auf Port 8000 zu).
2. Sende einen POST-Request an `/api/users/login` mit `X-Real-IP: 10.0.0.123` und falschen Credentials.
3. Wiederhole das 10-mal mit wechselnden `X-Real-IP` Headern.
4. Du wirst nicht geblockt, da das Fail2Ban-System denkt, es handele sich um 10 verschiedene Clients.

7. Root-Cause-Analyse
Die Annahme "Wenn `client_ip` privat ist, dann ist es unser Reverse Proxy und wir dürfen dem `X-Real-IP` Header vertrauen" ist fehlerhaft. In vielen Setups (besonders Docker/Self-Hosted) greifen Nutzer direkt mit einer privaten IP auf das System zu (z. B. 192.168.x.x oder VPN 10.x.x.x). In diesem Fall dürfen die Header nicht blind vertraut werden, da der Nutzer sie selbst setzen kann.

8. Impact
User-Impact: Andere Nutzer könnten fälschlicherweise durch IP-Spoofing ausgesperrt werden (Rate-Limit-Spoofing).
Daten-Impact: Keiner.
Security-Impact: Rate Limiting Bypass, IP Whitelisting Bypass (falls public IPs geblockt sind, ein Angreifer mit public IP aber eine Lücke findet, dies über einen SSRF oder internen Proxy mit privater IP zu schleusen und den Header zu setzen).
Performance-Impact: Keiner.

9. Fix-Richtung (kein Code, nur Strategie)
Konfiguriere Uvicorn so, dass es eine spezifische Liste von vertrauenswürdigen Proxies für `ForwardedAllowIPS` verwendet, oder baue eine Prüfung in `_resolve_client_ip` ein, die den Header nur akzeptiert, wenn die direkte `client.host` IP eine explizit konfigurierte Proxy-IP (wie die des Nginx-Containers) ist, und nicht generell jede private IP. Alternativ: ProxyHeadersMiddleware verwenden und richtig konfigurieren.

10. Test-Vorschlag
Teste `_resolve_client_ip` mit einem Mock-Request von einer privaten IP (z.B. 192.168.1.50) und `X-Real-IP: 8.8.8.8`. Die Funktion sollte nicht `8.8.8.8` zurückgeben, es sei denn `192.168.1.50` ist explizit als vertrauenswürdiger Proxy konfiguriert.

11. Referenzen
Verwandte Funktionen/Module im Repo: backend/api/utils/security.py
Externe Doku falls relevant: FastAPI/Uvicorn Proxy setup documentation.

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: IP Spoofing / Rate Limit Evasion via X-Real-IP / X-Forwarded-For

Aktueller Code:
```python
def _resolve_client_ip(request: Request) -> str:
    client_ip = request.client.host
    if not client_ip or not is_private_ip(client_ip):
        return client_ip

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
```

Bitte:
1. Ändere die Logik so ab, dass `X-Real-IP` und `X-Forwarded-For` nur von explizit erlaubten Proxy-IPs (z. B. aus einer Env-Var oder Config) akzeptiert werden, nicht von "jeder beliebigen privaten IP". (Fallback: ignoriere sie).
2. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
3. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll (z. B. ob Nutzer hinter Reverse-Proxies ihre IP in den Logs jetzt falsch sehen könnten, wenn sie den Proxy nicht konfigurieren).
