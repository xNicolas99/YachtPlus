"""B-07: Only one worker should lead the watchtower scheduler."""

import os
from unittest.mock import patch

from api.services import watchtower


def test_leader_lock_acquires_successfully(monkeypatch):
    tmp_dir = "/tmp/test_watchtower_leader"
    monkeypatch.setattr(watchtower.settings, "COMPOSE_DIR", tmp_dir + "/")

    # Clean state
    watchtower._scheduler_started = False

    assert watchtower._acquire_leader_lock() is True
    assert os.path.exists(os.path.join(tmp_dir, ".watchtower_leader.lock"))
