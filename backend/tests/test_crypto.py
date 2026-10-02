"""Tests for v2 (PBKDF2) crypto with v1 (legacy SHA-256) fallback."""
import base64
import hashlib
import os
import tempfile

import pytest
from cryptography.fernet import Fernet

from api.utils import crypto


@pytest.fixture(autouse=True)
def isolated_salt(tmp_path, monkeypatch):
    # Pin the salt file to a temp location so tests are hermetic and the
    # cached PBKDF2 key gets refreshed for each test.
    monkeypatch.setenv("FERNET_SALT_FILE", str(tmp_path / "salt"))
    monkeypatch.setattr(crypto, "_cached_fernet_key", None, raising=False)
    yield
    monkeypatch.setattr(crypto, "_cached_fernet_key", None, raising=False)


def test_encrypt_produces_v2_prefixed_token():
    token = crypto.encrypt("hello")
    assert token.startswith(crypto.V2_PREFIX)


def test_roundtrip_v2():
    token = crypto.encrypt("supersecret")
    assert crypto.decrypt(token) == "supersecret"


def test_legacy_v1_token_still_decryptable():
    # Manually construct a v1 token using the legacy key derivation.
    legacy_key = crypto._get_legacy_fernet_key()
    legacy_token = Fernet(legacy_key).encrypt(b"old-secret").decode()
    assert not legacy_token.startswith(crypto.V2_PREFIX)

    assert crypto.decrypt(legacy_token) == "old-secret"


def test_decrypt_empty_input_returns_input():
    assert crypto.decrypt("") == ""
    assert crypto.decrypt(None) is None


def test_encrypt_empty_input_returns_input():
    assert crypto.encrypt("") == ""
    assert crypto.encrypt(None) is None


def test_unrecognised_token_returns_input_unchanged():
    # Matches the legacy contract: garbage in -> garbage out (logged).
    assert crypto.decrypt("not-a-real-token") == "not-a-real-token"


def test_salt_persists_across_calls(tmp_path, monkeypatch):
    salt_file = tmp_path / "salt"
    monkeypatch.setenv("FERNET_SALT_FILE", str(salt_file))
    monkeypatch.setattr(crypto, "_cached_fernet_key", None, raising=False)

    crypto._get_fernet_key()
    first_salt = salt_file.read_bytes()

    # Reset cache, derive again, ensure same salt is reused.
    monkeypatch.setattr(crypto, "_cached_fernet_key", None, raising=False)
    crypto._get_fernet_key()
    assert salt_file.read_bytes() == first_salt


def test_v2_key_differs_from_legacy_key():
    """If v2 collapsed back to v1 derivation the migration is meaningless."""
    v2_key = crypto._get_fernet_key()
    v1_key = crypto._get_legacy_fernet_key()
    assert v2_key != v1_key


def test_v2_decrypt_failure_returns_input(monkeypatch):
    # Garbage v2-prefixed payload should not crash, just raise so callers
    # cannot mistake invalid ciphertext for a real secret.
    bogus = crypto.V2_PREFIX + "ZZZZ-not-valid-fernet"
    with pytest.raises(ValueError):
        crypto.decrypt(bogus)
