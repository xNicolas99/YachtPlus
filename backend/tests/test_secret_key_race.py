"""Race-safety test for SECRET_KEY creation (N-06)."""

import os
import tempfile
from concurrent.futures import ProcessPoolExecutor
from functools import partial


def _worker_secret(tmp_dir: str, _idx: int = 0) -> str:
    # Each worker imports settings in its own process and reads/creates the key.
    os.environ["SECRET_KEY_FILE"] = os.path.join(tmp_dir, ".secret_key")
    os.environ["SECRET_KEY"] = ""
    # Import must happen after env vars are set.
    from api.settings import get_or_create_secret_key

    return get_or_create_secret_key()


def test_multiprocess_secret_key_converges():
    with tempfile.TemporaryDirectory() as tmp_dir:
        worker = partial(_worker_secret, tmp_dir)
        with ProcessPoolExecutor(max_workers=8) as pool:
            keys = list(pool.map(worker, range(8)))

        assert all(k == keys[0] for k in keys), f"Keys diverged: {keys}"
        assert len(keys[0]) >= 32
        assert os.path.exists(os.path.join(tmp_dir, ".secret_key"))
