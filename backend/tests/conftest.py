"""Pytest configuration loaded before any test module imports.

Sets environment variables that must be in place before `api.settings`
is imported, because Settings class attributes are evaluated at class
definition time.
"""
import os

# Starlette's TestClient sends Host: testserver by default. Add it to the
# allowed-host list so TrustedHostMiddleware doesn't 400 every request.
os.environ.setdefault(
    "YACHT_ALLOWED_HOSTS",
    "localhost,127.0.0.1,[::1],testserver",
)
