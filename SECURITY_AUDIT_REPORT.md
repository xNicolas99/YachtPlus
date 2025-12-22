# Sicherheitsanalyse YachtPlus (Stand: 2.0.0)

## Zusammenfassung
Der Code von YachtPlus wurde hinsichtlich der Anforderungen des **BSI IT-Grundschutz (Baustein APP.3.1 Webanwendungen)**, der **BSI TR-02102 (Kryptographische Verfahren)** und der **ISO/IEC 27001 (Control 8.28 Secure Coding)** analysiert.

**Gesamtergebnis:** Die Anwendung erfüllt die aktuellen Sicherheitsstandards **nur teilweise**. Es wurden kritische Schwachstellen in den Bereichen Authentifizierung, Infrastruktur und Abhängigkeitsmanagement identifiziert, die vor einem produktiven Einsatz in sicherheitskritischen Umgebungen behoben werden müssen.

---

## 1. Kryptographie & Authentifizierung (BSI TR-02102 & APP.3.1)

### Befunde
*   **Passwort-Hashing (Konformität: Teilweise):**
    *   **Positiv:** Es wird `bcrypt` verwendet, was grundsätzlich BSI-konform ist.
    *   **Negativ:** Die verwendete Bibliothek `passlib` ist veraltet (v1.7.4, unmaintained seit 2017). Die `bcrypt`-Bibliothek ist ebenfalls veraltet (v3.2.2). Es besteht das Risiko, dass Sicherheitsupdates für diese Komponenten ausbleiben.
*   **Session-Management (Konformität: Kritisch):**
    *   **Kritisch:** Das `Secure`-Flag für Cookies ist hardcoded auf `False` (`backend/api/auth/jwt.py`). Damit werden Session-Cookies auch über unverschlüsselte HTTP-Verbindungen übertragen, was ein hohes Risiko für Session-Hijacking darstellt (Verstoß gegen BSI APP.3.1 A 3.2.1).
    *   **Positiv:** `HttpOnly`-Flag wird gesetzt.
*   **2-Faktor-Authentifizierung (Konformität: Kritisch):**
    *   **Kritisch:** Das TOTP-Secret (`user.otp_secret`) wird im Klartext in der Datenbank gespeichert. Bei einem Datenbank-Leak ist der zweite Faktor kompromittiert.
*   **Zufallszahlengenerierung:**
    *   Die Generierung des `SECRET_KEY` erfolgt mittels `secrets.token_hex(16)` (128 Bit Entropie), was für den verwendeten Algorithmus (HS256) akzeptabel, aber nicht optimal ist (BSI empfiehlt für hohe Sicherheit teils 256 Bit für HMAC-SHA256 Keys).

### Empfehlungen
1.  **Dependencies aktualisieren:** Migration auf aktuelle `passlib`-Alternativen oder direkte Nutzung einer aktuellen `bcrypt`-Implementierung.
2.  **Secure Flag aktivieren:** Das `Secure`-Flag für Cookies muss in Produktionsumgebungen zwingend aktiviert sein (konfigurierbar via Umgebungsvariable).
3.  **Secrets verschlüsseln:** Das 2FA-Secret sollte verschlüsselt in der Datenbank abgelegt werden (Encryption at Rest).

---

## 2. Webanwendungssicherheit (BSI APP.3.1 & ISO 27001 8.28)

### Befunde
*   **Cross-Site Scripting (XSS) (Konformität: Kritisch):**
    *   **Kritisch:** In mehreren Frontend-Komponenten (`TemplatesDetails.vue`, `ApplicationsForm.vue`) wird die Direktive `v-html` zur Ausgabe von Template-Notizen verwendet. Da Templates aus externen URLs geladen werden können, ermöglicht dies **Stored XSS**, falls ein Angreifer eine Template-Quelle kontrolliert.
*   **Injection-Risiken (Konformität: Teilweise):**
    *   **Command Injection:** Kritische Funktionen zur Docker-Steuerung nutzen Parameter direkt. Während keine offensichtliche Injection durch unvalidierten User-Input in Shell-Befehle gefunden wurde, ist die Architektur durch die direkte Nutzung von `docker.sock` und Volume-Mounts (User kann `/` mounten) inhärent risikobehaftet für Privilege Escalation.
    *   **SQL Injection:** Durch die konsequente Nutzung von SQLAlchemy ORM ist das Risiko für klassische SQL-Injection gering.
*   **Berechtigungen:**
    *   Es gibt ein Berechtigungssystem (`perm_start`, etc.), jedoch fehlt eine Granularität für das Erstellen von Containern. Ein User mit Deploy-Rechten kann Container mit Root-Mounts erstellen und so den Host übernehmen.

### Empfehlungen
1.  **XSS beheben:** Verwendung von `v-html` vermeiden oder Inhalte strikt mit einer Library wie `DOMPurify` bereinigen.
2.  **Eingabevalidierung verschärfen:** Striktes Whitelisting für Volume-Mounts einführen, um das Mounten sensibler Host-Pfade (`/`, `/etc`, `/proc`) zu verhindern.

---

## 3. Infrastruktur & Betrieb (ISO 27001 & BSI APP.3.1)

### Befunde
*   **Container-Privilegien (Konformität: Kritisch):**
    *   **Kritisch:** Der Backend-Prozess läuft im Container als `root`. In Kombination mit dem gemounteten Docker-Socket (`/var/run/docker.sock`) bedeutet dies, dass eine Kompromittierung der Anwendung zur vollständigen Übernahme des Host-Systems führt (Verstoß gegen Least-Privilege-Prinzip).
*   **Veraltete Softwarekomponenten (Patch-Management):**
    *   **Kritisch:** Zahlreiche Python-Bibliotheken sind auf veraltete Versionen "gepinnt" (`pydantic<2`, `SQLAlchemy<1.4`, `docker<7`). Dies verhindert das Einspielen von Sicherheitsupdates.
    *   Das Basis-Image `python:3.11-slim` ist aktuell, aber `node:16-alpine` im Build-Stage ist End-of-Life.

### Empfehlungen
1.  **Rootless Docker:** Umstellung des Containers auf einen nicht-privilegierten Benutzer (User Mapping).
2.  **Dependency-Upgrade:** Priorisiertes Refactoring des Backends, um Kompatibilität mit aktuellen Bibliotheksversionen (Pydantic V2, SQLAlchemy 2.0) herzustellen.
3.  **Docker Socket Proxy:** Einsatz eines Proxies (z.B. `tecnativa/docker-socket-proxy`) vor dem Docker-Socket, um den Zugriff auf gefährliche API-Endpunkte zu beschränken.

---

## Fazit

Der Code entspricht in wesentlichen Punkten **nicht** den Anforderungen für einen sicheren Betrieb nach BSI-Standard. Während grundlegende Mechanismen vorhanden sind, verhindern Architektur-Entscheidungen (Root-Prozesse, veraltete Libraries, fehlende XSS-Sanitization) eine positive Sicherheitszertifizierung. Eine Überarbeitung der genannten Punkte ist dringend angeraten.
