"""Encryption-at-rest support for personal data columns.

Uses Fernet (AES-128-CBC + HMAC) via a SQLAlchemy TypeDecorator so encryption
is transparent to the rest of the application. If no ENCRYPTION_KEY is
configured the value is stored as plaintext and a warning is logged once —
acceptable for local development only.
"""

import logging

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.config import get_settings

logger = logging.getLogger(__name__)

_PREFIX = "enc::"
_warned = False


def _get_fernet() -> Fernet | None:
    global _warned
    key = get_settings().encryption_key
    if not key:
        if not _warned:
            logger.warning(
                "ENCRYPTION_KEY is not set — personal data will be stored unencrypted. "
                "Set a Fernet key in production."
            )
            _warned = True
        return None
    return Fernet(key.encode())


def encrypt_value(value: str) -> str:
    f = _get_fernet()
    if f is None:
        return value
    return _PREFIX + f.encrypt(value.encode()).decode()


def decrypt_value(value: str) -> str:
    if not value.startswith(_PREFIX):
        return value
    f = _get_fernet()
    if f is None:
        raise RuntimeError("Encrypted value found but ENCRYPTION_KEY is not configured.")
    try:
        return f.decrypt(value[len(_PREFIX):].encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - key rotation misconfig
        raise RuntimeError("Failed to decrypt value — wrong ENCRYPTION_KEY?") from exc


class EncryptedString(TypeDecorator):
    """Column type that encrypts on write and decrypts on read."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_value(str(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return decrypt_value(value)
