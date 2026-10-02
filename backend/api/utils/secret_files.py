"""Publish complete secrets without exposing a partial file to other workers."""
import os
import tempfile
from pathlib import Path

def read_or_create_secret(path, generate, minimum, text=False):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        fd, temporary = tempfile.mkstemp(prefix=".secret-", dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(generate())
                file.flush()
                os.fsync(file.fileno())
            try:
                os.link(temporary, destination)
            except FileExistsError:
                pass
        finally:
            os.unlink(temporary)
    with destination.open("rb") as file:
        value = file.read(4097)
    if len(value) > 4096 or len(value.strip() if text else value) < minimum:
        raise RuntimeError("Persistent secret is empty or too short; restore it before starting")
    return value
