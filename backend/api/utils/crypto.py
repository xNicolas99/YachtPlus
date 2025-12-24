from cryptography.fernet import Fernet
import base64
import os
import hashlib
import logging

from api.settings import Settings

settings = Settings()
logger = logging.getLogger(__name__)

# Use the SECRET_KEY to derive a Fernet key
# Fernet key must be 32 url-safe base64-encoded bytes.
def get_fernet_key():
    secret = settings.SECRET_KEY
    if not secret:
        raise ValueError("SECRET_KEY is missing")

    # Hash the secret to ensure it's 32 bytes and consistent
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)

def encrypt(data: str) -> str:
    if not data:
        return data
    try:
        f = Fernet(get_fernet_key())
        return f.encrypt(data.encode()).decode()
    except Exception as e:
        logger.error(f"Encryption error: {e}")
        return data

def decrypt(token: str) -> str:
    if not token:
        return token
    try:
        f = Fernet(get_fernet_key())
        return f.decrypt(token.encode()).decode()
    except Exception as e:
        # Fallback to plain text if decryption fails (backward compatibility)
        logger.warning(f"Decryption failed, assuming plain text: {e}")
        return token
