# PROGRESS.md — Code-Audit & Vollüberarbeitung YachtPlus

> Historisches Arbeitsjournal zum Audit-Baseline-Commit `ee7fe6e` vom
> 2026-08-21. Die Tabellen, Commit-Verweise und Testzahlen darunter beschreiben
> diesen früheren Arbeitsstand, keine aktuelle Freigabe oder offene Aufgabenliste.
> Aktueller Abgleich am 2026-10-02: siehe `AGENTS.md`, `README.md` und den
> [aktuellen Behebungsbericht](docs/AUDIT_REMEDIATION_2026-10-02.md).
> Lokale Tests ersetzen weder einen
> laufenden Docker-Stack noch aktuelle GitHub-Checks.

## Präzisierungen zum aktuellen Checkout

- Vuex 4 ist alleiniger Store; Pinia ist weder installiert noch parallel aktiv.
  Die alte R1-Aufgabe ist damit keine notwendige Fehlerbehebung und keine
  zugesagte Migration. i18n/A11Y-Vorschläge unten bleiben historische Ideen.
- API-Keys sind GET/HEAD-only für Daten, mit bestehenden Benutzerrechten.
  Account-, Settings-, Docker-/Compose-Mutationen und Terminal sind gesperrt.
  Gespeichert werden JTI/Expiry und SHA-256(JTI), kein bcrypt-Hash des JWT.
- Audit-Logging ist asynchron und durch Mutations-/Login-Erfassung ergänzt.
  Die Speicherung in der Anwendungsdatenbank garantiert keine Unveränderlichkeit.
- Ältere grüne Paket-Audits und Testzahlen sind zeitbezogene Ergebnisse und
  kein Nachweis des aktuellen Zustands. Der aktuelle Kandidat benötigt die
  im Repository vorgeschriebenen Docker-/Laufzeitprüfungen vor Freigabe.

## Baseline

- Git-Tag: `baseline`
- Commit: `ee7fe6e` — baseline: uncommitted state before audit
- Backend-Tests: 501 grün
- Frontend-Tests: 21 grün
- pip-audit: 0 bekannte Vulns
- npm audit: 0 Vulns

## Befundstatus-Übersicht

| Severity | offen | behoben | akzeptiert |
|----------|-------|---------|------------|
| CRITICAL | 0     | 0       | 0          |
| HIGH     | 0     | 2       | 0          |
| MEDIUM   | 2     | 4       | 0          |
| LOW      | 1     | 3       | 0          |
| INFO     | 2     | 1       | 0          |

## Arbeitspakete (WORKLIST)

| # | ID | Kategorie | Befund-IDs | Änderung | Risiko | Verifikation | Status | Commit |
|---|----|-----------|------------|----------|--------|--------------|--------|--------|
| S1| fix(sec) | Sicherheit | FND-204, FND-201 | API-Key jti speichern + Widerruf in Blacklist | hoch | pytest 503 grün + neuer Test | erledigt | 170d6dc |
| S2| fix(sec) | Sicherheit | FND-401 | Deprecated GET-Aliase auf Mutations-Endpunkten entfernen | hoch | pytest 503 grün + npm build grün | erledigt | 83428a0 |
| S3| fix(sec) | Sicherheit | FND-101 | Audit-Log für WebSocket exec | mittel | pytest | erledigt | 6935938 |
| S4| fix(sec) | Sicherheit | FND-102, FND-104 | Stats-Streams AuthZ + Rate-Limiting vereinheitlichen | niedrig | pytest | erledigt | 6935938 |
| S5| fix(sec) | Sicherheit | FND-301 | Audit-Logging auf allen Mutations-Endpunkten vereinheitlichen; Integrität dokumentieren | mittel | pytest + Review | erledigt | 6935938 |
| S6| fix(sec) | Sicherheit | FND-205 | API-Key Scope einführen (`type=api_key`, Lifecycle-Actions blockiert) | mittel | pytest + Review | erledigt | e912f0f |
| S7| fix(sec) | Betriebsmodus | FND-501 | Startup-Modus-Check: widersprüchliche ENV-Kombinationen erkennen/warnen | mittel | pytest | erledigt | e912f0f |
| S8| refactor | Sicherheit/Performance | FND-601 | Sync docker-SDK Analyse; Call-Sites auf aiodocker prüfen | mittel | pytest + Review | erledigt | 6935938 |
| S9| refactor | Portabilität | FND-602 | .Jules/.jules Verzeichnis-Konflikt auflösen | niedrig | npm build + git status | erledigt | e912f0f |
| S10| chore | Sicherheit | FND-103 | Compose-Read-Berechtigung dokumentieren | info | Review | erledigt | e912f0f |
| R1| refactor | Frontend | FND-701 | Historischer Pinia-Vorschlag; aktuelle behauptete Doppelinstallation besteht nicht | mittel | Abgleich package.json/main.js am 2026-10-02 | nicht erforderlich | — |
| I1| feat(i18n) | Frontend/Backend | FND-702 | Vue I18n v11 + Vuetify-Adapter; Backend error.code additiv | mittel | npm build + 21 Tests + pytest | offen | — |
| U1| style(ui) | UI | — | A11Y-Fixes innerhalb Vuetify 3 | niedrig | npm build + Review | offen | — |

## Reihenfolge-Logik

1. S1, S2 (HIGH) zuerst — API-Key-Widerruf und CSRF-GET-Aliase haben direkte Sicherheitsrelevanz.
2. S3, S4, S5, S6 (MEDIUM) — AuthZ/Audit/Rate-Limiting konsistent machen.
3. S7 (Betriebsmodus) — fällt unter F4-Präzisierung, brechende API-Änderungen vermeidbar.
4. S8, S9 — Refactoring/Portabilität.
5. S10 — Dokumentation.
6. R1, I1, U1 — größere strukturelle Arbeiten, separierte Arbeitspakete; ggf. separater Auftrag, falls Scope zu groß.

## Nicht angefasst / bewusst verschoben

- R1 Pinia-Migration: Historischer Vorschlag; die zugrunde liegende Behauptung einer aktuellen Doppelinstallation ist korrigiert.
- I1 i18n: Große Oberflächen-Änderung; wird nur vorbereitet (error.code), nicht vollständig implementiert, falls Zeit/Scope es erfordern.
- U1 A11Y: Erfordert UI-Review, keine automatisierte Testabdeckung; niedrigste Priorität.

## Erledigte Schritte

- [x] Phase 0: Recon, Baseline-Commit `ee7fe6e`, Tag `baseline`
- [x] Phase 1: Klärungs-Gate freigegeben
- [x] Phase 2: Subagenten-Delegation (2 parallel erfolgreich: Code-Stand + Test-Infra)
- [x] Phase 3: Befundregister in `SECURITY-AUDIT.md`
- [x] Phase 4: Plan abgeschlossen
- [x] Phase 5: Umbau — S3-S5, S8 bereits in 6935938; S6, S7, S9, S10 in e912f0f umgesetzt
- [x] Phase 6: Verifikation — pytest 503/503 grün, npm audit 0, pip-audit 0, npm build grün
- [ ] Phase 7: Übergabe — Commit erstellt, Push erfordert Freigabe

## Blockierte / nicht angefasste Schritte

- R1 Pinia-Migration (FND-701): kein aktueller Fehler; Vuex 4 bleibt der einzige Store.
- I1 Vue I18n + error.code (FND-702): bewusst verschoben, separater Auftrag empfohlen.
- U1 A11Y-Fixes: keine automatisierte Testabdeckung, niedrigste Priorität.
