"""Machine activation: code derivation, signature verification, endpoint gate."""

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import licensing
from app.config import get_settings
from tests.conftest import TEST_PASSWORD

# Captured at import (collection) time, before the conftest autouse fixture
# replaces it with `lambda: True` for each test.
_REAL_IS_ACTIVATED = licensing.is_activated


def make_test_keypair(monkeypatch):
    """Point the module at a throwaway keypair and return a code signer."""
    private_key = Ed25519PrivateKey.generate()
    public_hex = private_key.public_key().public_bytes_raw().hex()
    monkeypatch.setattr(licensing, "PUBLIC_KEY_HEX", public_hex)

    def sign(machine_code: str) -> str:
        message = f"aip-licence:{licensing.normalise(machine_code)}".encode()
        return base64.b32encode(private_key.sign(message)).decode().rstrip("=")

    return sign


# --- Primitives -----------------------------------------------------------------


def test_machine_code_is_stable_and_formatted():
    code = licensing.machine_code()
    assert code == licensing.machine_code()
    parts = code.split("-")
    assert len(parts) == 4
    assert all(len(p) == 4 and p.isalnum() for p in parts)


def test_valid_code_verifies_and_survives_reformatting(monkeypatch):
    sign = make_test_keypair(monkeypatch)
    code = sign(licensing.machine_code())
    assert licensing.verify_activation_code(code)
    # Codes are retyped by humans: dashes, spaces, lowercase must not matter.
    scrambled = "-".join(code[i : i + 5] for i in range(0, len(code), 5)).lower()
    assert licensing.verify_activation_code(scrambled)


def test_invalid_codes_rejected(monkeypatch):
    sign = make_test_keypair(monkeypatch)
    good = sign(licensing.machine_code())
    assert not licensing.verify_activation_code("")
    assert not licensing.verify_activation_code("not a code")
    assert not licensing.verify_activation_code(good[:-4] + "AAAA")
    # A code signed for a DIFFERENT machine must not activate this one.
    assert not licensing.verify_activation_code(sign("XXXX-XXXX-XXXX-XXXX"))


# --- Endpoint gate ---------------------------------------------------------------


@pytest.fixture
def unactivated(monkeypatch):
    """Simulate a machine without a licence, with .env writes captured."""
    from app.api.routes import licence as licence_routes

    monkeypatch.setattr(licensing, "is_activated", _REAL_IS_ACTIVATED)
    monkeypatch.setattr(licensing, "_activated", None)
    monkeypatch.setattr(get_settings(), "licence_key", "")
    monkeypatch.setattr(licence_routes, "_FAILED_ATTEMPT_DELAY_SECONDS", 0)
    written = {}
    monkeypatch.setattr(
        licence_routes,
        "set_env_var",
        lambda name, value, env_path=None, comment=None: written.update({name: value}),
    )
    return written


async def test_everything_locked_until_activated(anon_client, unactivated):
    status = (await anon_client.get("/api/v1/licence/status")).json()
    assert status["activated"] is False
    assert status["machine_code"] == licensing.machine_code()

    resp = await anon_client.get("/api/v1/searches")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Activation required"

    # Login and setup are gated too — credentials don't bypass the licence.
    for path in ("/api/v1/auth/login", "/api/v1/auth/setup"):
        resp = await anon_client.post(
            path, json={"username": "admin", "password": TEST_PASSWORD}
        )
        assert resp.status_code == 403

    # Open endpoints keep working so auto-shutdown behaves normally.
    assert (await anon_client.get("/health")).status_code == 200


async def test_bad_activation_code_rejected(anon_client, unactivated, monkeypatch):
    make_test_keypair(monkeypatch)
    resp = await anon_client.post("/api/v1/licence/activate", json={"code": "WRONG"})
    assert resp.status_code == 400
    assert not unactivated


async def test_activation_unlocks_and_persists(anon_client, unactivated, monkeypatch):
    sign = make_test_keypair(monkeypatch)
    code = sign(licensing.machine_code())

    resp = await anon_client.post("/api/v1/licence/activate", json={"code": code})
    assert resp.status_code == 204
    assert unactivated["LICENCE_KEY"] == licensing.normalise(code)

    status = (await anon_client.get("/api/v1/licence/status")).json()
    assert status["activated"] is True
    # The lock is lifted: login now responds normally (401 = wrong password,
    # not 403 = unactivated).
    resp = await anon_client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert resp.status_code == 401
