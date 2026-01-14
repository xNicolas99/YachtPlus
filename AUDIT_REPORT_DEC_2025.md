# ELITE AUDIT REPORT - YACHT PLUS (DEZEMBER 2025)

**AUDITOR:** JULES (Elite System Auditor)
**DATUM:** 2025-12-01
**STATUS:** **KRITISCH**

Dieses Dokument ist das Ergebnis einer gnadenlosen Tiefenanalyse des YachtPlus Repositories. Es deckt massive Sicherheitslücken, technische Schulden und "Fassaden-Architektur" auf.

---

## 1. KRITISCHE ALARME (Sofortiger Handlungsbedarf)

### 🚨 ALARM 1: Die "Stub"-Lüge (Fassaden-Architektur)
**Status:** **TÄUSCHUNG**
Das Projekt gibt vor, auf Vue 3 migriert zu sein, aber kritische Bibliotheken werden in `vite.config.js` auf leere Stubs umgeleitet, um Build-Fehler zu vertuschen.
-   **Beweis:** `vite.config.js` -> `alias: { 'vee-validate': .../stubs/vee-validate.js', ... }`
-   **Konsequenz:**
    -   **Validierung:** `vee-validate` ist tot. Formulareingaben werden im Frontend möglicherweise nicht korrekt validiert (Sicherheitsrisiko & UX-Katastrophe).
    -   **Charts:** `vue-chartjs` ist tot. Dashboard-Graphen sind wahrscheinlich unsichtbar oder kaputt.
    -   **Editor:** `vue2-ace-editor` ist tot.
-   **Urteil:** Das ist kein Refactoring, das ist Sabotage der Code-Integrität.

### 🚨 ALARM 2: Zombie-Infrastruktur (Node 16)
**Status:** **EOL seit September 2023**
`frontend/package.json` fordert `"engines": { "node": ">=16" }`.
-   **Risiko:** Node 16 ist seit über zwei Jahren End-of-Life. Es erhält keine Security-Updates.
-   **Standard 2025:** Node 20 (LTS) oder Node 22 sind Pflicht.

### 🚨 ALARM 3: Scheunentor-Sicherheit (Wildcard Hosts)
**Status:** **HOCHRISIKO**
`backend/api/settings.py` setzt `ALLOWED_HOSTS` standardmäßig auf `["*"]`.
-   **Risiko:** DNS Rebinding Attacken. Ein Angreifer kann via präparierter Webseite im Browser des Admins interne Dienste ansprechen, da der Host-Header nicht validiert wird.
-   **Lösung:** Muss in Produktion zwingend auf die tatsächliche Domain/IP eingeschränkt werden.

---

## 2. SYSTEM-BREMSEN (Performance & Bloat)

### 🛑 BREMSE 1: Moment.js (Legacy Bloat)
**Status:** **DEPRECATED**
`frontend/src/plugins/vueutils.js` importiert `moment`.
-   **Problem:** Moment.js ist veraltet, nicht tree-shakeable und bläht das Bundle unnötig auf.
-   **Lösung:** Ersetzen durch `date-fns` oder natives `Intl.DateTimeFormat`.

### 🛑 BREMSE 2: Unsafe CSP
**Status:** **UNSAUBER**
`backend/api/main.py` erlaubt `'unsafe-eval'` in der Content Security Policy.
-   **Grund:** Überbleibsel aus Vue 2 Zeiten oder Nutzung von Runtime-Compilern.
-   **Konsequenz:** Schwächt den XSS-Schutz massiv.

---

## 3. ARCHITEKTUR-SÜNDEN

### 💀 SÜNDE 1: Inkonsistente Identität
-   Codebasis nennt sich "Yacht API" (`settings.py`), "YachtPlus" (README), Repository heißt anders.
-   Frontend nutzt Vuetify 3, aber Backend liefert teilweise noch Strukturen für alte Templates.

---

## 4. AUTONOME ROADMAP (Befehle für den Fixer)

Der folgende Plan muss strikt exekutiert werden, um den technischen Bankrott abzuwenden.

### SCHRITT 1: Infrastruktur härten
```bash
# 1. Node Version auf aktuellen Standard heben
sed -i 's/"node": ">=16"/"node": ">=20"/g' frontend/package.json

# 2. Veraltete Lockfiles bereinigen (erzwingt Neuinstallation mit Node 20)
rm -f frontend/package-lock.json
```

### SCHRITT 2: Sicherheits-Defaults setzen
```bash
# 3. Warnung für unsichere Host-Konfiguration einbauen (in settings.py oder main.py)
# (Manueller Eingriff empfohlen: Prüfe ALLOWED_HOSTS != ['*'])
```

### SCHRITT 3: Die Lüge beenden (Stubs entfernen)
Dies ist eine komplexe Aufgabe.
1.  Entferne die Aliases in `vite.config.js`.
2.  Installiere echte Vue 3 Kompatible Bibliotheken:
    -   `vee-validate` (v4)
    -   `vue-chartjs` (v5)
3.  Repariere den Code, der diese Bibliotheken nutzt.
    -   *Warnung:* Der Build wird fehlschlagen, bis dies erledigt ist.

**ABSCHLUSS-URTEIL:**
Das Projekt befindet sich in einem **instabilen Migrations-Zustand**. Die Nutzung von Stubs täuscht eine funktionierende Anwendung vor, während Kern-Features deaktiviert sind. Sofortige Remediation von Schritt 3 ist erforderlich.
