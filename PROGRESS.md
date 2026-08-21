# PROGRESS.md — Code-Audit & Vollüberarbeitung YachtPlus

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
| R1| refactor | Frontend | FND-701 | Pinia-Migration modulweise (scheut von Auth/Snackbar) | mittel | npm build + 21 Frontend-Tests | offen | — |
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

- R1 Pinia-Migration: Wurde als "separater Auftrag" vorgeschlagen, aber im Scope des Audits dokumentiert.
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

- R1 Pinia-Migration (FND-701): bewusst verschoben, separater Auftrag empfohlen.
- I1 Vue I18n + error.code (FND-702): bewusst verschoben, separater Auftrag empfohlen.
- U1 A11Y-Fixes: keine automatisierte Testabdeckung, niedrigste Priorität.
