"""Pytest configuration loaded before any test module imports.

Sets environment variables that must be in place before `api.settings`
is imported, because Settings class attributes are evaluated at class
definition time.
"""
import os
import tempfile

# Starlette's TestClient sends Host: testserver by default. Add it to the
# allowed-host list so TrustedHostMiddleware doesn't 400 every request.
os.environ.setdefault(
    "YACHT_ALLOWED_HOSTS",
    "localhost,127.0.0.1,[::1],testserver",
)

# Redirect SETUP_FLAG_FILE into the OS temp dir so test runs never touch
# /config (or D:\config on Windows). The setup-flag resolver only honours
# paths under /config or $cwd, so we override the env var to a path under
# cwd. Without this, a leftover .setup_completed from a prior run silently
# fails `assert is_setup_completed(db) is False` in the bypass tests.
_test_flag = os.path.join(os.getcwd(), ".pytest_setup_flag")
os.environ.setdefault("SETUP_FLAG_FILE", _test_flag)
try:
    if os.path.exists(_test_flag):
        os.remove(_test_flag)
except OSError:
    pass

# Don't seed default templates during tests — every call to add_template
# does a real network fetch to GitHub, which would slow the suite down and
# tie test outcomes to GitHub's uptime. Tests that exercise the seed path
# stub get_settings() themselves.
os.environ.setdefault("YACHT_DEFAULT_TEMPLATE_URLS", "")
