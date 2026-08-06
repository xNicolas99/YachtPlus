#!/usr/bin/env bash
#
# push-to-github.sh — Push the local YachtPlus work to your GitHub account.
#
# You only need to provide a GitHub Personal Access Token (PAT). The script
# then:
#   1. verifies the working tree is in a committable state,
#   2. creates a commit with a descriptive message,
#   3. points the remote at YOUR GitHub account (default: xNicolas99/YachtPlus),
#   4. pushes the current branch.
#
# The token is used ONLY for the push and is never written to disk or into
# the git history. It is passed via the remote URL for a single push and the
# remote is then reset to the plain (token-free) URL.
#
# Usage:
#   ./scripts/push-to-github.sh [--repo OWNER/REPO] [--message "msg"] [--token TOKEN]
#
# The token can be supplied in four ways (first match wins):
#   1. --token TOKEN
#   2. $GITHUB_TOKEN environment variable
#   3. a .env file in this script's directory (GITHUB_TOKEN=...)
#   4. interactive prompt (if stdin is a TTY)
#
# Examples:
#   GITHUB_TOKEN=ghp_xxx ./scripts/push-to-github.sh
#   ./scripts/push-to-github.sh --repo xNicolas99/YachtPlus --token ghp_xxx
#   # with a .env file next to the script:
#   echo 'GITHUB_TOKEN=ghp_xxx' > scripts/.env
#   ./scripts/push-to-github.sh
#
# How to create a token (https://github.com/settings/tokens):
#   - Fine-grained token, scope "Contents: Read and write" on the target repo,
#     or a classic token with the "repo" scope.
#
set -euo pipefail

# --- Config ---------------------------------------------------------------
REPO="${REPO:-xNicolas99/YachtPlus}"
BRANCH="$(git branch --show-current)"
DEFAULT_MSG="Async backend migration + frontend modernisation (lazy routes, Vuetify 3 cleanup, visibility-aware polling)"

# --- Load .env (optional) -------------------------------------------------
# If a .env file sits next to this script, source it so GITHUB_TOKEN (and
# REPO) can be provided without typing them on the command line. The file
# is git-ignored and never committed.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.env"
  set +a
fi

# --- Parse args -----------------------------------------------------------
TOKEN=""
MESSAGE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)   REPO="${2:?--repo needs OWNER/REPO}"; shift 2 ;;
    --message) MESSAGE="$2"; shift 2 ;;
    --token)  TOKEN="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# --- Resolve token --------------------------------------------------------
if [[ -z "$TOKEN" ]]; then
  TOKEN="${GITHUB_TOKEN:-}"
fi
if [[ -z "$TOKEN" ]]; then
  if [[ -t 0 ]]; then
    read -r -s -p "GitHub Personal Access Token: " TOKEN
    echo
  else
    echo "ERROR: no token provided. Use --token, \$GITHUB_TOKEN, a scripts/.env file, or run interactively." >&2
    exit 1
  fi
fi

# --- Sanity checks --------------------------------------------------------
if [[ -z "$BRANCH" ]]; then
  echo "ERROR: not on a branch (detached HEAD)." >&2
  exit 1
fi
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: not inside a git repository." >&2
  exit 1
fi

# --- Ensure a git identity exists -----------------------------------------
# A fresh clone has no user.name/user.email, which makes `git commit` fail
# with "unable to auto-detect email address". Derive one from the target
# repo owner so the commit can be created without manual setup.
if [[ -z "$(git config user.name)" ]]; then
  OWNER="${REPO%%/*}"
  git config user.name "$OWNER"
  echo "==> Set local git user.name to '$OWNER'"
fi
if [[ -z "$(git config user.email)" ]]; then
  git config user.email "${REPO%%/*}@users.noreply.github.com"
  echo "==> Set local git user.email to '${REPO%%/*}@users.noreply.github.com'"
fi

# --- Stage everything -----------------------------------------------------
# Stage all changes. scripts/.env is covered by .gitignore (and .env*), so a
# plain `git add -A` silently skips it — no warning, no token committed.
# (Avoid pathspec excludes here: adding a `:(exclude)` pathspec makes git
# treat the tree as "explicitly requested" and then warn about the ignored
# .env file, which is noisy and confusing.)
echo "==> Staging all changes..."
git add -A

if git diff --cached --quiet; then
  echo "==> Nothing to commit — working tree is clean."
  echo "    (If you already committed, the push below still runs.)"
else
  echo "==> Creating commit..."
  git commit -m "${MESSAGE:-$DEFAULT_MSG}"
fi

# --- Push -----------------------------------------------------------------
# Build a token-scoped URL for a single push, then restore the clean URL.
AUTH_URL="https://x-access-token:${TOKEN}@github.com/${REPO}.git"
CLEAN_URL="https://github.com/${REPO}.git"

echo "==> Pushing branch '${BRANCH}' to ${REPO} ..."
# Capture the push result so we can ALWAYS restore the clean remote URL,
# even when the push fails (auth error, network, etc.). The token must
# never linger in the remote config.
PUSH_OK=0
if git push "$AUTH_URL" "${BRANCH}:${BRANCH}"; then
  PUSH_OK=1
else
  echo "ERROR: push failed (see output above)." >&2
fi

# Reset the remote to the token-free URL so the token never lingers in config.
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$CLEAN_URL"
fi

if [[ "$PUSH_OK" -ne 1 ]]; then
  echo "Remote origin reset to: $CLEAN_URL" >&2
  exit 1
fi

echo
echo "==> Done. Pushed ${BRANCH} to https://github.com/${REPO}"
