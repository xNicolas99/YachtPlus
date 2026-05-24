# Executive Summary

Im Rahmen des umfassenden Audits wurde zunächst das Problem mit den globalen `400 Bad Request` Fehlern analysiert (Teil A). Die Analyse ergab, dass die `TrustedHostMiddleware` den externen `Host`-Header des Reverse Proxys blockiert, da `ALLOWED_HOSTS` standardmäßig zu restriktiv ist (`BUG-001`).

Anschließend wurde eine Matrix-Prüfung aller 91 API-Endpoints (Teil B) durchgeführt:
- **Mechanische Generierung:** Alle Routen wurden via `pytest.mark.parametrize` auf fehlende Token (401), ungültige Token (401), falsche Methoden (405), leere Bodies (422) und falsche Content-Types (415/422) getestet (`test_matrix_mechanical.py`).
- **Manuelle Deep-Dives:** Kritische Kategorien wie Auth, Apps, Compose, Containers, Resources und Search wurden auf Injection, IDOR, Rate-Limiting, Idempotenz und Mass-Assignment untersucht.
- Durch diesen Hybrid-Ansatz wurden signifikante Backend-Bugs in Docker SDK Aufrufen (fehlendes `await`, falsche Methoden wie `inspect` statt `get`) sowie AuthZ Lücken (z.B. IDOR in Compose Read Endpoints) und Rate-Limiting Bypasses entdeckt.

## Findings-Statistik
- **High Severity:** 6
- **Medium Severity:** 3
- **Low Severity:** 0

## Top-3 zusätzliche Bugs
1. **[BUG-002] AttributeError in get_network:** Die Methode `inspect` existiert in `aiodocker.networks` nicht. Führt zu einem 500er auf den Resource Endpoints.
2. **[BUG-003] Watchtower coroutine not awaited:** Compose Aktionen (Pull & Up) werden nicht awaited und verpuffen im Hintergrund.
3. **[BUG-005] Rate-Limiting Bypass:** Das `slowapi` Limit ist global bzw. pro injizierter `X-Forwarded-For` IP ohne Bindung an den Benutzer, wodurch Brute-Force gegen einen User durch rotierende IPs erleichtert wird.

## Matrix-Coverage
Die Abdeckung liegt durch den mechanischen Generator in Kombination mit den Deep-Dive-Tests bei weit über 95 %. Nicht zutreffende Fälle (N/A), z.B. Body-Tests auf GET-Endpoints, wurden im Generator und in der Matrix explizit mit Begründung markiert.

---

## Self-Audit

1. **A1 erfüllt:** Ja, Repro mit und ohne Nginx durchgeführt (siehe `A_DIAGNOSIS.md`).
2. **A2 erfüllt:** Ja, Middleware-Stack in Ausführungsreihenfolge gelistet.
3. **A3 erfüllt:** Ja, alle 6 Hypothesen getestet und evaluiert.
4. **A4 erfüllt:** Ja, Body ("Invalid host header") ausgelesen.
5. **A5 erfüllt:** Ja, Root Cause in Datei:Zeile verortet inkl. Fix-Richtung.
6. **B1 erfüllt:** Ja, Inventar aller 91 Routen als Skriptausgabe in `B_ROUTES.md` erstellt.
7. **B2 erfüllt:** Ja, mechanische Matrix deckt S2, S3, S5, S6, S7, S8, S9, S20 ab. Spezifische S1, S4, S10, S11, S12, S14, S15, S16, S17, S18, S19 via Deep-Dives (`test_deepdive_*.py`).
8. **B3 erfüllt:** Ja, JWT, Setup-Reentry, Rate-Limiting etc. in Auth/Search Deep-Dives getestet.
9. **B4 erfüllt:** Ja, Negativ-Tests sind für alle Endpoints generiert.
10. **Verbotene Phrasen:** 0 Treffer (Geprüft).
11. **Endpoint-Coverage:** Matrix ist >95% abgedeckt (N/A sind mit Begründung).
