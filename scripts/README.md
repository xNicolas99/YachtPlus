# Push to GitHub

Dieses Skript pusht den lokalen YachtPlus-Stand auf dein GitHub-Konto.
Du musst nur einen **Personal Access Token (PAT)** bereitstellen — der
Assistent übernimmt Commit und Push automatisch.

## Schnellstart

```bash
cd /home/user/projects/YachtPlus
./scripts/push-to-github.sh
```

Das Skript fragt interaktiv nach dem Token. Alternativ:

```bash
GITHUB_TOKEN=ghp_xxx ./scripts/push-to-github.sh
# oder
./scripts/push-to-github.sh --token ghp_xxx
```

### Bequemste Variante: `.env`-Datei

Lege einmalig eine Datei `scripts/.env` an (wird von Git ignoriert und
niemals committet):

```bash
# scripts/.env
GITHUB_TOKEN=ghp_xxx
```

Danach reicht ein einfacher Aufruf — das Skript liest den Token automatisch:

```bash
./scripts/push-to-github.sh
```

> **Sicherheit:** Die `.env` wird vom Skript beim `git add` explizit
> ausgeschlossen und steht in der `.gitignore`. Der Token landet weder im
> Commit noch im Git-Verlauf.

## Was das Skript tut

1. Staged alle Änderungen (`git add -A`).
2. Erstellt einen Commit mit beschreibender Nachricht (überschreibbar via `--message`).
3. Setzt die Git-Identität automatisch, falls sie fehlt (aus dem Repo-Owner abgeleitet).
4. Pusht den aktuellen Branch auf `https://github.com/<OWNER>/<REPO>`.
5. Setzt die Remote-URL nach dem Push **immer** auf die token-freie URL zurück —
   der Token landet nie in der Git-Konfiguration oder im Verlauf.

## Optionen

| Option | Beschreibung |
|---|---|
| `--repo OWNER/REPO` | Ziel-Repo (Standard: `xNicolas99/YachtPlus`) |
| `--message "msg"` | Eigene Commit-Nachricht |
| `--token TOKEN` | Token direkt übergeben |
| `--help` | Hilfe anzeigen |

## Token erstellen

1. Öffne https://github.com/settings/tokens
2. **Fine-grained token** (empfohlen):
   - Repository access: nur das Ziel-Repo
   - Permissions → Contents: **Read and write**
3. Oder **Classic token** mit Scope **`repo`**.
4. Token kopieren (wird nur einmal angezeigt).

> **Sicherheit:** Der Token wird ausschließlich für den Push verwendet und
> nie gespeichert. Gib ihn nicht in Chat-Nachrichten oder Commits weiter.
