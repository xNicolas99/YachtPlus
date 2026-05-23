# BUG-007

Severity: Medium
Kategorie: Other
Confidence: Medium (statisch erkannt)
Erstmals erkannt in: frontend/src/components/applications/ApplicationDeployFromTemplate.vue
Related Bugs: none

1. Zusammenfassung (2–3 Sätze)
In mehreren Vue-Komponenten (z. B. `ApplicationDeployFromTemplate.vue`, `ApplicationsForm.vue`, `TemplatesDetails.vue`) wird `v-html` in Verbindung mit `$sanitize` verwendet, um Notizen oder Beschreibungen zu rendern. Obwohl `$sanitize` verwendet wird (vermutlich DOMPurify), warnt die statische Analyse vor XSS-Risiken. Wenn `$sanitize` in seiner Konfiguration nicht extrem restriktiv ist oder Bugs aufweist, können bösartige Inhalte gerendert werden, insbesondere da Benutzer oder Vorlagen-Maintainer diese Notizen kontrollieren.

2. Betroffene Stellen
Datei: frontend/src/components/applications/ApplicationDeployFromTemplate.vue
Zeilen: 124
Datei: frontend/src/components/applications/ApplicationsForm.vue
Zeilen: 16
Datei: frontend/src/components/templates/TemplatesDetails.vue
Zeilen: 112
Rolle: Frontend Vue Templates

3. Code-Snippet
```vue
<p v-if="selectedApp.notes" v-html="$sanitize(selectedApp.notes)" />
```

4. Erwartetes Verhalten
Wenn reines Text-Rendern nicht ausreicht und HTML benötigt wird, muss `$sanitize` garantiert fehlerfrei sein. Wenn reiner Text gemeint ist, sollte stattdessen Interpolation (`{{ }}`) verwendet werden.

5. Tatsächliches Verhalten
HTML-Inhalte werden (gefiltert) gerendert.

6. Reproduktion
Da `$sanitize` DOMPurify verwendet (laut README), ist eine tatsächliche XSS-Ausnutzung nur bei einem Bypass von DOMPurify möglich. Deshalb bleibt es ein Medium-Risk Verdachtsfall aus statischer Analyse. Claude sollte prüfen, ob `v-html` wirklich nötig ist oder ob es zu reiner Textausgabe migriert werden kann.

7. Root-Cause-Analyse
Verwendung von dynamischem HTML-Rendering (`v-html`) anstatt Template-Interpolation.

8. Impact
User-Impact: Risiko von Cross-Site Scripting (XSS), falls `$sanitize` versagt.
Daten-Impact: keiner
Security-Impact: Medium.
Performance-Impact: keiner

9. Fix-Richtung
Wenn die Notes keine Formatierungen enthalten, ersetze `v-html` durch Standard-Interpolation `{{ selectedApp.notes }}`. Wenn HTML erlaubt sein soll, validiere die Konfiguration von `$sanitize` und dokumentiere, warum XSS ausgeschlossen ist.

10. Test-Vorschlag
Versuche, ein `<img src=x onerror=alert(1)>` Tag als Note zu speichern und prüfe, ob es ausgeführt wird.

11. Referenzen
Verwandte Dateien: `frontend/src/main.js` (Wo `$sanitize` konfiguriert wird).

📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

Hi Claude, bitte prüfe/fixe den folgenden Bug-Verdacht. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.

Bug: Verdacht auf XSS durch v-html

Aktueller Code:
```vue
<p v-if="selectedApp.notes" v-html="$sanitize(selectedApp.notes)" />
```

Bitte:
1. Prüfe, ob `v-html` hier wirklich notwendig ist. Wenn nicht, stelle auf `{{ selectedApp.notes }}` um.
2. Erkläre kurz, ob `$sanitize` hier ausreichend schützt, falls `v-html` bleiben muss.
