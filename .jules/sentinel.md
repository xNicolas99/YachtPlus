## 2025-05-13 - Overly Permissive CORS Policy

**Vulnerability:** The `CORSMiddleware` in `backend/api/main.py` was configured with `allow_origins=["*"]` while `allow_credentials=True`. This configuration is insecure as it allows any website to make credentialed requests (including cookies/auth headers) to the API, potentially leading to Cross-Site Request Hijacking (CSRF) or unauthorized data access if session cookies are used. Furthermore, most modern browsers block this specific combination for security reasons.

**Learning:** Wildcard origins should never be used in conjunction with `allow_credentials=True`. Configuration for CORS should always be externalized and restricted to a whitelist of trusted domains to maintain a strong security posture.

**Prevention:**
1. Always use a specific whitelist for `allow_origins` when `allow_credentials` is `True`.
2. Externalize the origin whitelist via environment variables to allow different configurations for development, staging, and production.
3. Provide safe, restricted defaults (e.g., localhost only) rather than open wildcards.

## 2025-05-17 - Prevent Argument Injection via Subprocess Validation
**Vulnerability:** Argument Injection Risk via Subprocess
**Learning:** `subprocess.run` command line argument values can be interpreted as flags if they begin with a hyphen.
**Prevention:** Always validate user-provided values used as part of subprocess command arguments with regex that disallows a leading hyphen.
