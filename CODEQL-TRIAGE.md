# CodeQL Alert Triage

This file documents triage decisions for GitHub CodeQL findings in this
repository.  Valid issues are fixed in code; findings that are false positives
in our specific context are dismissed via the GitHub API with the reason and
reference recorded here so the decision is auditable.

## Open alerts (post-triage)

None after the fixes documented below are merged.

## Dismissed / not-a-finding

### Alert #22 — Clear-text storage of sensitive information

- **Rule:** `py/clear-text-storage-sensitive-data`
- **Location:** `backend/api/settings.py:45`
- **GitHub URL:** `https://github.com/xNicolas99/YachtPlus/security/code-scanning/22`
- **Reason:** The finding flags the in-memory presence of `SECRET_KEY` in the
  `Settings` object.  The secret is read from a configured file at runtime and
  must exist as plain bytes in process memory so PyJWT can sign and verify
  access tokens.  It is **not** written to persistent storage, logs, cookies,
  or the frontend.  This is the expected and unavoidable runtime state for any
  JWT-signing service.
- **Action:** Dismissed as `false_positive`.

## Fixed findings

| Alert | Rule | Location | Fix summary |
|------:|------|----------|-------------|
| #25 | `py/weak-sensitive-data-hashing` | `backend/api/db/crud/users.py:236` | API-key bearer token is now hashed with bcrypt before storage; `APIKEY.hashed_key` column widened from 72 to 255 characters to accommodate the bcrypt string. |
| #24 | `py/incomplete-url-substring-sanitization` | `backend/api/utils/registries.py:330` | Registry detection now uses `urllib.parse` via new helper `api/utils/registry_helpers.py`. |
| #23 | `py/incomplete-url-substring-sanitization` | `backend/api/utils/image_inspect.py:14` | Same helper-based registry detection. |
| #18 | `py/incomplete-url-substring-sanitization` | `backend/api/utils/image_inspect.py:17` | Same helper-based registry detection. |
