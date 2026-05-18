## 2025-05-13 - Overly Permissive CORS Policy

**Vulnerability:** The `CORSMiddleware` in `backend/api/main.py` was configured with `allow_origins=["*"]` while `allow_credentials=True`. This configuration is insecure as it allows any website to make credentialed requests (including cookies/auth headers) to the API, potentially leading to Cross-Site Request Hijacking (CSRF) or unauthorized data access if session cookies are used. Furthermore, most modern browsers block this specific combination for security reasons.

**Learning:** Wildcard origins should never be used in conjunction with `allow_credentials=True`. Configuration for CORS should always be externalized and restricted to a whitelist of trusted domains to maintain a strong security posture.

**Prevention:**
1. Always use a specific whitelist for `allow_origins` when `allow_credentials` is `True`.
2. Externalize the origin whitelist via environment variables to allow different configurations for development, staging, and production.
3. Provide safe, restricted defaults (e.g., localhost only) rather than open wildcards.
## 2025-02-23 - Prevent Argument Injection via Regex Validation
**Vulnerability:** User-controlled inputs like app names or project names, even when validated against `^[a-zA-Z0-9_-]+$`, could start with a hyphen. If passed to `subprocess.run`, they might be interpreted as command-line flags rather than positional arguments, leading to argument injection vulnerabilities (even with `shell=False`).
**Learning:** The previous regex allowed inputs like `-d` or `--rm` which could modify command execution behavior.
**Prevention:** Use a stricter regex such as `^[a-zA-Z0-9][a-zA-Z0-9_-]*$` that requires the first character to be an alphanumeric character, effectively preventing leading hyphens and argument injection vulnerabilities in subprocess calls.
