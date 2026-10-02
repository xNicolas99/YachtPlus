# CodeQL Alert Triage

This file documents triage decisions for GitHub CodeQL findings in this
repository. It preserves historical decisions and references. A local code
review does not confirm the current GitHub dismissal/open-alert state.
Implementation corrections below were checked against the checkout on
2026-10-02; use live GitHub code-scanning results to establish alert status.

## Open alerts (post-triage)

The earlier report stated that none remained after its fixes were merged.
Current live alert status has not been established by this document.

## Dismissed / not-a-finding

### Alert #22 — Clear-text storage of sensitive information

- **Rule:** `py/clear-text-storage-sensitive-data`
- **Location:** `backend/api/settings.py:45`
- **GitHub URL:** `https://github.com/xNicolas99/YachtPlus/security/code-scanning/22`
- **Reason:** The finding flags the in-memory presence of `SECRET_KEY` in the
  `Settings` object.  The secret is read from a configured file at runtime and
  must exist as plain bytes in process memory so PyJWT can sign and verify
  access tokens. The earlier claim that it is never written to persistent
  storage was inaccurate: when not explicitly supplied, YachtPlus persists
  it at `SECRET_KEY_FILE` in a mode-0600 file published atomically. It must
  never enter logs, cookies or frontend responses. Whether the historical
  alert concerned required memory state or that intended persistent file
  must be assessed from the alert's actual data flow.
- **Historical action:** Recorded as `false_positive`; no new dismissal is
  established or performed by this document.

## Fixed findings

| Alert | Rule | Location | Fix summary |
|------:|------|----------|-------------|
| #25 | `py/weak-sensitive-data-hashing` | `backend/api/db/crud/users.py` | Current implementation hashes the random JTI with SHA-256 and stores its 64-character hex digest. It does not bcrypt-hash the bearer JWT; bcrypt's 72-byte limit would truncate a JWT. JWT signature, active key record, JTI blacklist and account version provide authentication/revocation. |
| #24 | `py/incomplete-url-substring-sanitization` | `backend/api/utils/registries.py:330` | Registry detection now uses `urllib.parse` via new helper `api/utils/registry_helpers.py`. |
| #23 | `py/incomplete-url-substring-sanitization` | `backend/api/utils/image_inspect.py:14` | Same helper-based registry detection. |
| #18 | `py/incomplete-url-substring-sanitization` | `backend/api/utils/image_inspect.py:17` | Same helper-based registry detection. |
