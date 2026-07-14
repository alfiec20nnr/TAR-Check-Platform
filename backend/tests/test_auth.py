"""Single-user login: hashing, session tokens, endpoint guard, setup flow."""

import time

import pytest

from app import auth
from app.config import get_settings
from tests.conftest import TEST_PASSWORD


# --- Primitives -----------------------------------------------------------------


def test_password_hash_roundtrip():
    hashed = auth.hash_password("s3cret-value", iterations=1000)
    assert auth.verify_password("s3cret-value", hashed)
    assert not auth.verify_password("wrong", hashed)
    # Salted: same password hashes differently each time.
    assert hashed != auth.hash_password("s3cret-value", iterations=1000)


def test_verify_password_rejects_malformed_hashes():
    assert not auth.verify_password("anything", "")
    assert not auth.verify_password("anything", "not-a-hash")
    assert not auth.verify_password("anything", "md5$1$abc$def")


def test_session_token_roundtrip_tamper_and_expiry():
    token = auth.create_session_token()
    assert auth.verify_session_token(token)
    assert not auth.verify_session_token(token + "x")
    assert not auth.verify_session_token("garbage")
    # Forged expiry without a matching signature.
    expiry, _, signature = token.partition(".")
    assert not auth.verify_session_token(f"{int(expiry) + 999}.{signature}")
    # Expired token, correctly signed.
    past = int(time.time()) - 10
    expired = f"{past}.{auth._sign(f'aip-session:{past}')}"
    assert not auth.verify_session_token(expired)


# --- Endpoint guard -------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/api/v1/searches", "/api/v1/dashboard/stats", "/api/v1/sources"],
)
async def test_protected_endpoints_reject_anonymous(anon_client, path):
    resp = await anon_client.get(path)
    assert resp.status_code == 401


async def test_open_endpoints_allow_anonymous(anon_client):
    assert (await anon_client.get("/health")).status_code == 200
    assert (await anon_client.post("/api/v1/session/open")).status_code == 204
    assert (await anon_client.post("/api/v1/session/close")).status_code == 204


async def test_login_grants_access_and_logout_revokes(anon_client):
    resp = await anon_client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": TEST_PASSWORD}
    )
    assert resp.status_code == 204
    assert auth.COOKIE_NAME in anon_client.cookies

    assert (await anon_client.get("/api/v1/searches")).status_code == 200

    status = (await anon_client.get("/api/v1/auth/status")).json()
    assert status == {"configured": True, "authenticated": True}

    assert (await anon_client.post("/api/v1/auth/logout")).status_code == 204
    assert (await anon_client.get("/api/v1/searches")).status_code == 401


@pytest.mark.parametrize(
    "credentials",
    [
        {"username": "admin", "password": "wrong-password"},
        {"username": "someone-else", "password": TEST_PASSWORD},
    ],
)
async def test_login_rejects_bad_credentials(anon_client, credentials, monkeypatch):
    from app.api.routes import auth as auth_routes

    monkeypatch.setattr(auth_routes, "_FAILED_LOGIN_DELAY_SECONDS", 0)
    resp = await anon_client.post("/api/v1/auth/login", json=credentials)
    assert resp.status_code == 401
    assert auth.COOKIE_NAME not in anon_client.cookies


# --- First-launch setup ---------------------------------------------------------


@pytest.fixture
def unconfigured(monkeypatch, tmp_path):
    """Simulate a first launch: no password hash, .env writes go to tmp."""
    from app.api.routes import auth as auth_routes

    settings = get_settings()
    monkeypatch.setattr(settings, "auth_password_hash", "")
    # The setup endpoint mutates auth_username on the cached settings too;
    # re-setting it to itself registers the original value for restore.
    monkeypatch.setattr(settings, "auth_username", settings.auth_username)
    written = {}

    def fake_set_env_var(name, value, env_path=None, comment=None):
        written[name] = value

    monkeypatch.setattr(auth_routes, "set_env_var", fake_set_env_var)
    return written


async def test_setup_required_before_configuration(anon_client, unconfigured):
    status = (await anon_client.get("/api/v1/auth/status")).json()
    assert status == {"configured": False, "authenticated": False}

    resp = await anon_client.get("/api/v1/searches")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Initial setup required"

    resp = await anon_client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "whatever"}
    )
    assert resp.status_code == 401


async def test_setup_creates_credentials_and_logs_in(anon_client, unconfigured):
    resp = await anon_client.post(
        "/api/v1/auth/setup", json={"username": "alice", "password": "longenough"}
    )
    assert resp.status_code == 204
    assert unconfigured["AUTH_USERNAME"] == "alice"
    assert auth.verify_password("longenough", unconfigured["AUTH_PASSWORD_HASH"])

    # Setup logs the user straight in and updates live settings.
    assert (await anon_client.get("/api/v1/searches")).status_code == 200
    resp = await anon_client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "longenough"}
    )
    assert resp.status_code == 204


async def test_setup_rejects_short_password(anon_client, unconfigured):
    resp = await anon_client.post(
        "/api/v1/auth/setup", json={"username": "alice", "password": "short"}
    )
    assert resp.status_code == 422


async def test_setup_conflicts_once_configured(anon_client):
    resp = await anon_client.post(
        "/api/v1/auth/setup", json={"username": "eve", "password": "longenough"}
    )
    assert resp.status_code == 409
