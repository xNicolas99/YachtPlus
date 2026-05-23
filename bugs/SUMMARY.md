# Bug Hunt Summary

## Stack-Übersicht
- **Sprachen**: Python 3 (Backend), JavaScript/Vue (Frontend)
- **Frameworks**: FastAPI (Backend), Vue 3 + Vuetify (Frontend)
- **DB**: SQLite (via SQLAlchemy)
- **Auth**: JWT in HttpOnly Cookies, 2FA (TOTP/pyotp)
- **Test-Framework**: pytest (Backend), vitest (Frontend)
- **Build-Tool**: npm/vite (Frontend), docker (Full Stack)
- **Einstiegspunkt(e)**: `backend/api/main.py` (Backend), `frontend/src/main.js` (Frontend)

## Bug-Statistik
- **Critical:** 1
- **High:** 0
- **Medium:** 3
- **Low:** 4
- **Suspicion:** 0

- **Kategorie Injection:** 1
- **Kategorie ErrorHandling:** 3
- **Kategorie Config:** 1
- **Kategorie Auth:** 1
- **Kategorie Other:** 2

## Top-kritischste Bugs
1. **BUG-001 (Critical): Beliebige Codeausführung via Container-Start (Arbitrary Container Run)**
   Fehlende Validierung beim Aufruf von Docker SDK `run` ermöglicht RCE auf dem Host durch bösartige App-Templates.
2. **BUG-002 (Medium): Hardcoded Bcrypt Hash (Dummy Hash)**
   Ein hartkodierter Hash verringert die Robustheit der Timing-Attack-Mitigierung im Vergleich zu Bibliotheks-Funktionen.
3. **BUG-004 (Medium): Potenzielles Binden an alle Interfaces (0.0.0.0)**
   Fallback-IP `0.0.0.0` beim Container-Binding kann zur unerwünschten Exposition von Diensten führen.

## Cluster-Analyse
- **BUG-003, BUG-006, BUG-008:** Gehören zum Cluster "ErrorHandling Anti-Pattern". Sie alle nutzen ein bare `except: pass`, was dazu führt, dass Fehler beim Ausführen, Parsen oder bei Netzwerk-Requests stillschweigend unterdrückt werden und nicht im Log erscheinen.

## Empfohlene Fix-Reihenfolge
1. **BUG-001**: Höchste Priorität, da RCE / Host-Kompromittierung.
2. **BUG-002**: Auth-System-Verbesserung, sollte schnell repariert werden.
3. **BUG-004**: Potenzieller Security-Risiko, wenn Configs falsch verstanden werden.
4. **Restliche Bugs (BUG-003, BUG-005, BUG-006, BUG-007, BUG-008)**: Code-Qualitäts- und Stabilitätsverbesserungen, können als Block oder nebenbei gepatcht werden.

## Was wurde NICHT geprüft
- Manuelle Prüfung der Vue-Frontend-Komponenten auf XSS, CSRF oder State-Management-Race-Conditions. (Fokus lag auf Backend-Statik).
- Die Geschäftslogik in den Actions (außerhalb der gemeldeten Sicherheitsregeln von Semgrep), wie z. B. komplexe Race-Conditions bei der parallelen Abarbeitung von Background-Jobs oder tiefgreifende Tests der JWT-Rotation.
- Laufzeitverhalten bei Skalierung (Concurrency, Locking auf DB-Ebene), da dies ein "Read-Only-Audit" ohne echten Stresstest ist.

## Verwendete Tools & Versionen
- Python 3.12.13
- ruff (0.15.14)
- bandit (1.9.4)
- semgrep (1.163.0)
