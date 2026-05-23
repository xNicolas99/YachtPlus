"""Defense-in-depth whitelist for the docker-compose action names that
reach subprocess.run. Subprocess uses the array form so this isn't a
shell-injection vector today, but a typo or future caller that skips the
router-level whitelist must still be rejected.
"""
import pytest
from unittest.mock import patch
from fastapi import HTTPException

from api.actions import compose as actions_compose


@pytest.mark.parametrize("bad_action", [
    "; rm -rf /",
    "rm",          # valid for app actions, not for project actions
    "logs",
    "exec sh",
    "",
    "../up",
    "UP",          # case-sensitive
])
def test_project_action_rejects_non_whitelisted(bad_action):
    with pytest.raises(HTTPException) as exc:
        actions_compose._compose_action_sync("demo", bad_action)
    assert exc.value.status_code == 400
    assert "Invalid compose action" in exc.value.detail


@pytest.mark.parametrize("bad_action", [
    "; rm -rf /",
    "delete",      # valid for project actions, not for app
    "logs",
    "",
    "EXEC",
])
def test_app_action_rejects_non_whitelisted(bad_action):
    with pytest.raises(HTTPException) as exc:
        actions_compose._compose_app_action_sync("demo", bad_action, "svc")
    assert exc.value.status_code == 400


def test_whitelist_constants_are_disjoint_where_expected():
    """`delete` only makes sense for whole projects; `rm` only for a single
    service inside a project. Pinning that here so a refactor doesn't
    accidentally widen either set."""
    assert "delete" in actions_compose._ALLOWED_PROJECT_ACTIONS
    assert "delete" not in actions_compose._ALLOWED_APP_ACTIONS
    assert "rm" in actions_compose._ALLOWED_APP_ACTIONS
    assert "rm" not in actions_compose._ALLOWED_PROJECT_ACTIONS


def test_whitelist_contains_no_shell_metacharacters():
    for entry in (
        actions_compose._ALLOWED_PROJECT_ACTIONS
        | actions_compose._ALLOWED_APP_ACTIONS
    ):
        for bad in (" ", ";", "|", "&", "$", "`", "\\"):
            assert bad not in entry, f"{entry!r} contains {bad!r}"
