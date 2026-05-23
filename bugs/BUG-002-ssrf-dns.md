# BUG-002

Severity: High
Kategorie: Validation
Confidence: High (statisch erkannt)
Erstmals erkannt in: backend/api/db/crud/templates.py
Related Bugs: none

1. Zusammenfassung (2–3 Sätze)
Die Funktion `validate_url` überprüft, ob der Hostname einer Template-URL auf private IP-Adressen verweist, um Server-Side Request Forgery (SSRF) zu verhindern. Allerdings wird die URL nach der Validierung erneut durch `urllib.request.build_opener(SafeRedirectHandler()).open(url)` aufgerufen. Dieser "Time-of-Check to Time-of-Use" (TOCTOU) Gap macht die Applikation anfällig für DNS Rebinding-Angriffe, bei denen die erste DNS-Anfrage eine legitime öffentliche IP und die zweite (beim tatsächlichen HTTP-Request) eine interne IP liefert.

2. Betroffene Stellen
Datei: backend/api/db/crud/templates.py
Zeilen: 38 (validate_url Aufruf) und 42 (urllib fetch)
Rolle: Hauptort des Bugs

3. Code-Snippet
```python
def add_template(db: Session, template: models.Template):
    validate_url(template.url) # Check (resolves DNS)
    _template = models.Template(title=template.title, url=template.url)

    try:
        # Use (resolves DNS again)
        payload = _fetch_template_payload(template.url)
...
def _fetch_template_payload(url: str):
    opener = urllib.request.build_opener(SafeRedirectHandler())
    with opener.open(url, timeout=TEMPLATE_FETCH_TIMEOUT_S) as file:
```

4. Erwartetes Verhalten
Der HTTP-Client sollte nicht anhand des Hostnamens, sondern direkt anhand der zuvor validierten IP-Adresse (unter Beibehaltung des `Host`-Headers) verbinden, oder auf Netzwerk-Ebene (z.B. über ein isoliertes Proxy-Interface) davon abgehalten werden, interne IPs zu erreichen.

5. Tatsächliches Verhalten
Ein Angreifer kann eine Domain bereitstellen, die bei der ersten Auflösung (während `validate_url`) eine externe IP liefert. Unmittelbar danach ändert sich der DNS-Eintrag (oder die Antwort alterniert), sodass der anschließende `urllib`-Aufruf eine private IP (z.B. 127.0.0.1, 169.254.169.254) kontaktiert. Da die URL intern vom Server angefordert wird, ermöglicht dies SSRF.

6. Reproduktion
Schritt-für-Schritt:
1. Erstelle eine DNS-Rebinding-Domain (z.B. über Dienste wie rebind.network), die zwischen `8.8.8.8` und `127.0.0.1` wechselt.
2. Sende einen Request an `/api/templates/` (POST) mit dieser URL.
Beobachtung: Manchmal schlägt `validate_url` fehl (wenn 127.0.0.1 zuerst kommt), manchmal gelingt beides, und manchmal geht `validate_url` durch und der Fetcher greift erfolgreich auf interne Ressourcen zu.

7. Root-Cause-Analyse
Es gibt eine Diskrepanz zwischen Validierung und Verwendung (TOCTOU). `urllib` führt seine eigene DNS-Auflösung durch, die von der Auflösung in `validate_url` abweichen kann.

8. Impact
User-Impact: keiner
Daten-Impact: keiner
Security-Impact: SSRF erlaubt den Zugriff auf das interne Netzwerk des Docker-Hosts, Cloud-Metadaten (z. B. AWS IAM Tokens auf 169.254.169.254) oder auf interne ungesicherte APIs.
Performance-Impact: keiner

9. Fix-Richtung
Ersetze `urllib` durch einen dedizierten Fetcher, der sich mit der bereits aufgelösten, validierten IP verbindet und den originalen Hostnamen als `Host`-Header übergibt. Da SSL mit IPs oft an Zertifikatsvalidierungen scheitert, könnte man auch einen angepassten HostResolver im Client (z. B. mit `httpx`) nutzen, der die validierte IP festnagelt.

10. Test-Vorschlag
Erstelle einen Mock für `socket.getaddrinfo`, der abwechselnd eine öffentliche und eine private IP zurückgibt. Der Test sollte sicherstellen, dass `_fetch_template_payload` blockiert wird oder die öffentliche IP nutzt.

11. Referenzen
Verwandte Funktionen: `validate_url`, `_fetch_template_payload` in `backend/api/db/crud/templates.py`

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: DNS Rebinding Vulnerability in Template Fetching

Aktueller Code:
```python
def add_template(db: Session, template: models.Template):
    validate_url(template.url) # Führt DNS Lookup durch
    _template = models.Template(title=template.title, url=template.url)

    try:
        # Führt neuen DNS Lookup durch -> TOCTOU / SSRF
        payload = _fetch_template_payload(template.url)
...
def _fetch_template_payload(url: str):
    opener = urllib.request.build_opener(SafeRedirectHandler())
    with opener.open(url, timeout=TEMPLATE_FETCH_TIMEOUT_S) as file:
```

Bitte:
1. Implementiere den Fix mit minimaler Änderung. Nutze z.B. einen custom HTTP(S)Connection Pool in `urllib` oder wechsle zu einem sicheren Fetcher (wie `httpx` mit festem Transport), um die validierte IP direkt zu verwenden (Host-Header erhalten!).
2. Schreibe den Regressionstest aus §10 (einen Mock, der Rebinding simuliert).
3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
