# ASSUMPTIONS.md — Code-Audit YachtPlus

## Phase-1-Klärungen (vom Nutzer bestätigt/korrigiert)

[A-001] 2026-08-21 AGENTS.md:1
Unklarheit:     Welche Design-Richtung für UI-Fixes?
Gewählt:        (C) Vuetify 3 beibehalten, kein Restyle
Begründung:     Eigene 21 Frontend-Tests existieren; Restyle würde sie brechen ohne Sicherheitsgewinn.
Alternative:    (A) Vanilla-Styling — billiger, aber inkonsistent mit Vuetify
Umkehraufwand:  hoch

[A-002] 2026-08-21 ASSUMPTIONS.md:10
Unklarheit:     Wie tief darf API/CLI umgebaut werden?
Gewählt:        (B) Öffentliche API-Shape stabil halten
Begründung:     API-Keys existieren für Fremdcode; Image ist auf ghcr.io veröffentlicht. Request/Response-Shapes, Cookie-Name, Auth-Flow, YACHT_* ENV, DOCKER_HOST, docker-compose-Interface, DB-Schema via Alembic müssen stabil bleiben.
Alternative:    (C) frei umbauen — bei externen Konsumenten zu riskant
Umkehraufwand:  hoch

[A-003] 2026-08-21 ASSUMPTIONS.md:18
Unklarheit:     i18n-Lösung und Default-Sprache
Gewählt:        de + en, Default en, Ansprache "du", Vue I18n v11 Composition API legacy:false; Vuetify über createVueI18nAdapter angebunden
Begründung:     Vue-3-Standard, vermeidet halb übersetzte UI. Backend liefert error-CODE zusätzlich zur message (nicht ersetzend).
Alternative:    Eigene Minimallösung — geringerer Eingriff, aber schlechtere Vuetify-Integration
Umkehraufwand:  mittel

[A-004] 2026-08-21 ASSUMPTIONS.md:27
Unklarheit:     Betriebsmodell und Trust Boundary
Gewählt:        Zwei gleichberechtigte Modi: LOKAL (Default) und ÖFFENTLICH (Opt-in). Härtungsniveau sinkt NICHT für lokalen Modus; internes LAN ist keine Vertrauenszone.
Begründung:     Docker-Daemon-Steuerung = hoher Impact in beiden Modi. Übergang zwischen Modi wird als eigener Befundkatalog geprüft.
Alternative:    Nur lokal optimieren — falsch wegen IoT/Gastnetze/DNS-Rebinding
Umkehraufwand:  hoch

[A-005] 2026-08-21 ASSUMPTIONS.md:36
Unklarheit:     Budget Subagenten / Websuche
Gewählt:        3 parallele Subagenten; Websuche per Probe-Auftrag, ohne weiter falls nicht verfügbar
Begründung:     Begrenzte Ressourcen, aber ausreichend für parallele Analysestränge.
Alternative:    Mehr parallele Subagenten — riskant wegen CPU/RAM-Limit
Umkehraufwand:  gering

[A-006] 2026-08-21 ASSUMPTIONS.md:43
Unklarheit:     Warum laufen aiodocker und docker-SDK parallel?
Gewählt:        Zunächst Analyse durch Subagenten, Fix ergibt sich aus Befunden
Begründung:     Blockierende SDK-Aufrufe im async Pfad, Connection-Leaks, Races, unterschiedliche Timeouts sind mögliche Befundklassen. Voreiliges Aufräumen könnte Funktionalität zerstören.
Alternative:    Sofort docker-SDK entfernen — könnte kritische Pfade brechen
Umkehraufwand:  hoch

[A-007] 2026-08-21 ASSUMPTIONS.md:52
Unklarheit:     Pinia + Vuex 4 parallel — was tun?
Gewählt:        Modulweise Migration zu Pinia, nie Big Bang; Frontend-Tests nach jedem Modul grün
Begründung:     Zwei Zustandsquellen für denselben Zustand (insb. auth) ist Befundklasse. Stufenweise Migration reduziert Regressionen.
Alternative:    Sofort alles auf Pinia — zu großer Schritt bei 21 Frontend-Tests
Umkehraufwand:  hoch

## Eigene Annahmen während des Audits

[A-008] 2026-08-21 ASSUMPTIONS.md:75
Unklarheit:     pip-audit ist nicht installiert, benötigt Freigabe?
Gewählt:        Installation als Dev/Test-Dependency, kein Produktionsartefakt
Begründung:    pip-audit dient ausschließlich der Audit-Phase und wird nicht ins Docker-Image/Release übernommen.
Alternative:    Manuelle CVE-Liste zusammenstellen — unvollständig
Umkehraufwand: gering

