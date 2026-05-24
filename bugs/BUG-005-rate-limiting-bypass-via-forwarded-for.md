# BUG-005: Rate-Limiting bypass potential via X-Forwarded-For

- **Severity:** High
- **Kategorie:** Auth
- **Confidence:** High
- **Sweep-Quelle:** B2-S16 (Deep Dive)
- **Erstmals erkannt in:** `backend/api/utils/security.py` / `_resolve_client_ip`
- **Related Bugs:** none

## 1. Zusammenfassung
Der Endpunkt `/api/auth/login` nutzt `slowapi` zur Limitierung der Login-Versuche (5 pro Minute). Wenn der Header `X-Forwarded-For` verwendet wird und der Trusted Proxy dies durchreicht (bzw. nicht richtig eingeschränkt ist), kann ein Angreifer durch einfaches Ändern der IP in `X-Forwarded-For` den Rate-Limiter umgehen. Im Test funktionierte das Limit für dieselbe IP korrekt (gab 429), aber mit wechselnder IP greift die `slowapi`-Drosselung erst für die neue IP. Die zusätzliche Counter-Logik pro Username (`_USERNAME_LOCKOUT_WINDOW_MIN`) hilft, greift aber erst nach 20 Versuchen (`_USERNAME_LOCKOUT_THRESHOLD`).

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|---|---|---|
| `backend/api/routers/users.py` | 137 | `@limiter.limit("5/minute")` |
| `backend/api/utils/security.py` | 120 | `_count_recent_failed_attempts_for_username` (Threshold=20) |

## 3. Code-Snippet
```python
@router.post("/login")
@limiter.limit("5/minute")
def login(...)
```

## 4. Erwartetes Verhalten
Bei einem Brute-Force-Angriff auf einen einzelnen Benutzernamen über verschiedene IPs sollte die Drosselung pro Benutzername (z. B. 5 Versuche) greifen.

## 5. Tatsächliches Verhalten
Das Rate-Limit von 5/minute gilt strikt pro IP. Der Counter pro Benutzername greift erst nach 20 Versuchen. Damit sind 20 Brute-Force Versuche auf ein Passwort pro 30 Minuten möglich.

## 6. Reproduktion
Schleife, die bei jedem Request eine andere IP in den gemockten Resolver/Header injiziert.

## 7. Root-Cause-Analyse
`slowapi` verwendet als Key standardmäßig `get_remote_address`. Es gibt keinen kombinierten Limiter `(IP, Username)`, daher muss sich die App auf den DB-basierten Lockout (`_count_recent_failed_attempts_for_username`) verlassen, der mit 20 recht hoch eingestellt ist.

## 8. Impact
Security (High): Verteiltes Brute-Force-Raten von Passwörtern gegen denselben Benutzer ist mit 20 Versuchen / 30 Min möglich.

## 9. Fix-Richtung
Den Wert `_USERNAME_LOCKOUT_THRESHOLD` in `api/utils/security.py` von 20 auf 5 oder 10 reduzieren.

## 10. Test-Vorschlag
Regelmäßige Login-Fehlschläge für denselben User über verschiedene IPs sollten spätestens ab Versuch 5 blockiert werden.
