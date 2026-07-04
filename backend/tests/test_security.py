"""Encryption-at-rest tests."""

from cryptography.fernet import Fernet

from app import security
from app.config import get_settings


def test_plaintext_when_no_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "encryption_key", "")
    assert security.encrypt_value("Jane Doe") == "Jane Doe"
    assert security.decrypt_value("Jane Doe") == "Jane Doe"


def test_encrypt_decrypt_roundtrip(monkeypatch):
    settings = get_settings()
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "encryption_key", key)

    ciphertext = security.encrypt_value("Jane Doe")
    assert ciphertext != "Jane Doe"
    assert ciphertext.startswith("enc::")
    assert "Jane" not in ciphertext
    assert security.decrypt_value(ciphertext) == "Jane Doe"


def test_legacy_plaintext_still_readable_with_key(monkeypatch):
    """Values written before encryption was enabled must remain readable."""
    settings = get_settings()
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    assert security.decrypt_value("Jane Doe") == "Jane Doe"
