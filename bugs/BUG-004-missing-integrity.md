# BUG-004

Severity: Medium
Kategorie: Other
Confidence: High (statisch erkannt)
Erstmals erkannt in: frontend/index.html
Related Bugs: none

1. Zusammenfassung (2–3 Sätze)
In `frontend/index.html` wird das Material Design Icons Stylesheet über ein externes CDN (`jsdelivr.net`) geladen. Es fehlt das `integrity`-Attribut (Subresource Integrity, SRI), das sicherstellt, dass die Datei nicht auf dem Weg oder auf dem CDN durch einen Angreifer kompromittiert wurde. Dadurch kann im Ernstfall bösartiger CSS- (und evtl. JS-ähnlicher) Code in den Client eingeschleust werden (z. B. Keylogging via CSS).

2. Betroffene Stellen
Datei: frontend/index.html
Zeilen: 15
Rolle: Frontend HTML-Template

3. Code-Snippet
```html
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@mdi/font@latest/css/materialdesignicons.min.css">
```

4. Erwartetes Verhalten
Extern gehostete Skripte und Stylesheets müssen mit einem gültigen `integrity`-Hash versehen sein. Zusätzlich sollte aus Performance- und Determinismusgründen eine explizite Versionsnummer statt `@latest` verwendet werden, da `@latest` ohnehin einen spezifischen Hash für SRI ungültig macht.

5. Tatsächliches Verhalten
Es wird auf das CDN vertraut und die neuste Version ohne Überprüfung der Integrität geladen.

6. Reproduktion
Schritt-für-Schritt:
Betrachte `frontend/index.html` Zeile 15.
Beobachtung: `<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@mdi/font@latest/css/materialdesignicons.min.css">` ohne `integrity`-Attribut.

7. Root-Cause-Analyse
Fehlende Nutzung von SRI für externe Ressourcen und Nutzung von `@latest`, was den Build nicht-deterministisch macht.

8. Impact
User-Impact: Alle User des Frontends.
Daten-Impact: keiner
Security-Impact: Risiko von Frontend-Compromise im Falle eines CDN-Hacks.
Performance-Impact: keiner

9. Fix-Richtung
Fixiere die Version von `@mdi/font` in der URL (z. B. `@7.4.47`) und füge den entsprechenden SHA-Hash über das `integrity`-Attribut hinzu (und setze `crossorigin="anonymous"`).

10. Test-Vorschlag
Ein einfacher Parser-Test, der sicherstellt, dass alle `<link>` und `<script>`-Tags, die auf CDN-Domains verweisen, das Attribut `integrity` aufweisen.

11. Referenzen
Verwandte Funktionen: `index.html`

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: Fehlendes SRI-Attribut in index.html

Aktueller Code:
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@mdi/font@latest/css/materialdesignicons.min.css">
```

Bitte:
1. Implementiere den Fix mit minimaler Änderung. Ersetze `@latest` durch eine feste Version und füge `integrity` und `crossorigin="anonymous"` hinzu.
2. Schreibe den Regressionstest aus §10 nicht für HTML, aber korrigiere die Datei.
3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
