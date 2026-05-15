## 2025-05-13 - Overly Permissive CORS Policy

**Vulnerability:** The `CORSMiddleware` in `backend/api/main.py` was configured with `allow_origins=["*"]` while `allow_credentials=True`. This configuration is insecure as it allows any website to make credentialed requests (including cookies/auth headers) to the API, potentially leading to Cross-Site Request Hijacking (CSRF) or unauthorized data access if session cookies are used. Furthermore, most modern browsers block this specific combination for security reasons.

**Learning:** Wildcard origins should never be used in conjunction with `allow_credentials=True`. Configuration for CORS should always be externalized and restricted to a whitelist of trusted domains to maintain a strong security posture.

**Prevention:**
1. Always use a specific whitelist for `allow_origins` when `allow_credentials` is `True`.
2. Externalize the origin whitelist via environment variables to allow different configurations for development, staging, and production.
3. Provide safe, restricted defaults (e.g., localhost only) rather than open wildcards.
## 2026-05-15 - Argument Injection via Leading Hyphens

**Vulnerability:** The `validate_app_name` and `validate_compose_project_name` functions allowed strings starting with hyphens (`-`) because their validation regex was `^[a-zA-Z0-9_-]+$`. When these names were subsequently passed to `subprocess.run()` (e.g., executing `docker-compose up -d <app>`), an attacker could prepend a hyphen to the app or project name, causing it to be evaluated as an arbitrary command-line flag (argument injection).

**Learning:** Validation rules for strings destined for shell or subprocess command arguments must explicitly forbid leading characters that act as flag prefixes (like hyphens) to prevent injection, even when `shell=False`.

**Prevention:**
1. Modify validation regexes for command arguments to explicitly enforce an alphanumeric starting character (e.g., `^[a-zA-Z0-9][a-zA-Z0-9_-]*$`).
2. Consistently sanitize inputs passed to any execution context (like `subprocess.run`) using strict allow-lists that account for how the execution context parses arguments.
