"""Symmetric encryption helpers for at-rest secrets (e.g. TOTP seeds).

Two key derivations are supported:

* **v2 (current)** - PBKDF2-HMAC-SHA256 over ``SECRET_KEY`` with a persisted
  per-deployment salt and 600 000 iterations (NIST SP 800-132 recommendation
  for SHA-256 as of 2024). Tokens are prefixed with ``v2:``.
* **v1 (legacy, read-only)** - single SHA-256 of ``SECRET_KEY``, no salt, no
  iterations. Only used to decrypt tokens that predate v2.

Migration is opportunistic: any value successfully decrypted via the v1 path
gets re-encrypted with v2 the next time the caller writes it back
(``encrypt``). There is no in-place rewriter, so dormant v1 ciphertexts
remain readable until the model row is updated.
"""

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import hashlib
import logging
import os
import secrets

from api.settings import get_settings
_settings = get_settings()

logger = logging.getLogger(__name__)

V2_PREFIX = "v2:"
_PBKDF2_ITERATIONS = 600_000
_SALT_BYTES = 16


def _salt_path() -> str:
    # Mirror the SECRET_KEY discovery strategy so persistence works the same
    # whether we're in a container (/config) or running locally.
    candidate = os.getenv("FERNET_SALT_FILE", "/config/.fernet_salt")
    config_dir = os.path.dirname(candidate)
    if config_dir and not os.path.exists(config_dir):
        return ".fernet_salt"
    return candidate


def _load_or_create_salt() -> bytes:
    path = _salt_path()
    if os.path.exists(path):
        with open(path, "rb") as f:
            salt = f.read()
        if len(salt) >= _SALT_BYTES:
            return salt
        logger.warning("Fernet salt at %s is too short; regenerating.", path)

    salt = secrets.token_bytes(_SALT_BYTES)
    try:
        with open(path, "wb") as f:
            f.write(salt)
    except OSError as exc:
        raise RuntimeError(
            f"Could not persist Fernet salt at {path!r}: {exc}. Set FERNET_SALT_FILE "
            "to a writable path."
        ) from exc
    return salt


# Cache the derived key. SECRET_KEY and salt are both immutable for the
# process lifetime, so we only pay the PBKDF2 cost once per startup.
_cached_fernet_key: bytes | None = None


def _get_fernet_key() -> bytes:
    global _cached_fernet_key
    if _cached_fernet_key is not None:
        return _cached_fernet_key

    secret = get_settings().SECRET_KEY
    if not secret:
        raise ValueError("SECRET_KEY is missing")

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_load_or_create_salt(),
        iterations=_PBKDF2_ITERATIONS,
    )
    derived = kdf.derive(secret.encode())
    _cached_fernet_key = base64.urlsafe_b64encode(derived)
    return _cached_fernet_key


def _get_legacy_fernet_key() -> bytes:
    """Pre-v2 key derivation: single SHA-256 over SECRET_KEY, no salt."""
    secret = get_settings().SECRET_KEY
    if not secret:
        raise ValueError("SECRET_KEY is missing")
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt(data: str) -> str:
    if not data:
        return data
    try:
        token = Fernet(_get_fernet_key()).encrypt(data.encode()).decode()
        return V2_PREFIX + token
    except Exception as e:
        logger.error(f"Encryption error: {e}")
        raise RuntimeError("Failed to encrypt sensitive data") from e


def decrypt(token: str) -> str:
    if not token:
        return token

    if token.startswith(V2_PREFIX):
        try:
            return Fernet(_get_fernet_key()).decrypt(token[len(V2_PREFIX):].encode()).decode()
        except InvalidToken as e:
            logger.warning("v2 decryption failed: %s", e)
            raise ValueError("Decryption failed: invalid token") from e

    # Legacy path: token has no v2 prefix. Try the old SHA-256 key derivation.
    try:
        return Fernet(_get_legacy_fernet_key()).decrypt(token.encode()).decode()
    except InvalidToken:
        # Not a recognised ciphertext - matches prior behaviour of returning
        # the input unchanged so older plaintext records continue to work.
        logger.warning("Decryption failed for both v2 and legacy keys; returning input as-is.")
        return token
    except Exception as e:
        logger.warning("Unexpected decryption error: %s", e)
        raise RuntimeError("Failed to decrypt sensitive data") from e
