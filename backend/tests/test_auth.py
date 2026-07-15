"""Login: hashing, session tokens with identity, endpoint guard, setup flow."""

import time

import pytest
from sqlalchemy import delete, select

from app import auth
from app.database import get_session_factory
from app.models import User
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
    token = auth.create_session_token("admin")
    assert auth.verify_session_token(token) == "admin"
    assert auth.verify_session_token(token + "x") is None
    assert auth.verify_session_token("garbage") is None
    # Forged expiry without a matching signature.
    username_b64, expiry, signature = token.split(".")
    forged = f"{username_b64}.{int(expiry) + 999}.{signature}"
    assert auth.verify_session_token(forged) is None
    # Forged username with someone else's signature.
    other = auth._b64encode("someone-else")
    assert auth.verify_session_token(f"{other}.{expiry}.{signature}") is None
    # Expired token, correctly signed.
    past = int(time.time()) - 10
    expired = f"{auth._b64encode('admin')}.{past}.{auth._sign(f'aip-session:admin:{past}')}"
    assert auth.verify_session_token(expired) is None


def test_legacy_identityless_token_rejected():
    """Cookies minted before multi-user accounts (no username) fail closed."""
    expires = int(time.time()) + 3600
    legacy = f"{expires}.{auth._sign(f'aip-session:{expires}')}"
    assert auth.verify_session_token(legacy) is None


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
    assert status == {"configured": True, "authenticated": True, "username": "admin"}

    assert (await anon_client.post("/api/v1/auth/logout")).status_code == 204
    assert (await anon_client.get("/api/v1/searches")).status_code == 401


async def test_login_is_case_insensitive_on_username(anon_client):
    resp = await anon_client.post(
        "/api/v1/auth/login", json={"username": "  ADMIN ", "password": TEST_PASSWORD}
    )
    assert resp.status_code == 204


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


async def test_logins_are_audited(client, anon_client, monkeypatch):
    from app.api.routes import auth as auth_routes

    monkeypatch.setattr(auth_routes, "_FAILED_LOGIN_DELAY_SECONDS", 0)
    await anon_client.post(
        "/api/v1/auth/login", json={"username": "intruder", "password": "nope"}
    )
    entries = (await client.get("/api/v1/audit")).json()
    succeeded = [e for e in entries if e["action"] == "login_succeeded"]
    assert succeeded and succeeded[0]["actor"] == "admin"
    failed = [e for e in entries if e["action"] == "login_failed"]
    assert failed and failed[0]["details"]["username"] == "intruder"
    assert failed[0]["actor"] is None


# --- Session revocation ----------------------------------------------------------


async def _set_active(username: str, active: bool) -> None:
    async with get_session_factory()() as session:
        user = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one()
        user.is_active = active
        await session.commit()


async def test_disabled_user_is_revoked_on_next_request(client):
    assert (await client.get("/api/v1/searches")).status_code == 200
    await _set_active("admin", False)
    # The cookie is still validly signed, but the account check fails closed.
    assert (await client.get("/api/v1/searches")).status_code == 401
    await _set_active("admin", True)
    assert (await client.get("/api/v1/searches")).status_code == 200


async def test_deleted_user_is_revoked_on_next_request(client):
    async with get_session_factory()() as session:
        await session.execute(delete(User).where(User.username == "admin"))
        await session.commit()
    assert (await client.get("/api/v1/searches")).status_code == 401


# --- Cookie flags ----------------------------------------------------------------


async def test_secure_cookie_flag_follows_setting(anon_client, settings, monkeypatch):
    monkeypatch.setattr(settings, "session_cookie_secure", True)
    resp = await anon_client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": TEST_PASSWORD}
    )
    cookie_header = resp.headers["set-cookie"]
    assert "Secure" in cookie_header
    assert "HttpOnly" in cookie_header


# --- Change password --------------------------------------------------------------


async def test_change_password(client, anon_client, monkeypatch):
    from app.api.routes import auth as auth_routes

    monkeypatch.setattr(auth_routes, "_FAILED_LOGIN_DELAY_SECONDS", 0)

    wrong = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "not-right", "new_password": "brand-new-pass"},
    )
    assert wrong.status_code == 401

    short = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "short"},
    )
    assert short.status_code == 422

    ok = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "brand-new-pass"},
    )
    assert ok.status_code == 204

    # Old password no longer works; the new one does.
    old = await anon_client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": TEST_PASSWORD}
    )
    assert old.status_code == 401
    new = await anon_client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "brand-new-pass"}
    )
    assert new.status_code == 204

    # And the change is audited.
    entries = (await client.get("/api/v1/audit")).json()
    changed = [e for e in entries if e["action"] == "password_changed"]
    assert changed and changed[0]["actor"] == "admin"


async def test_change_password_requires_login(anon_client):
    resp = await anon_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "x", "new_password": "brand-new-pass"},
    )
    assert resp.status_code == 401


# --- First-launch setup ---------------------------------------------------------


@pytest.fixture
async def unconfigured(settings, monkeypatch):
    """Simulate a fresh install: no accounts and no legacy env credentials."""
    monkeypatch.setattr(settings, "auth_password_hash", "")
    async with get_session_factory()() as session:
        await session.execute(delete(User))
        await session.commit()


async def test_setup_required_before_configuration(anon_client, unconfigured):
    status = (await anon_client.get("/api/v1/auth/status")).json()
    assert status == {"configured": False, "authenticated": False, "username": None}

    resp = await anon_client.get("/api/v1/searches")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Initial setup required"

    resp = await anon_client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "whatever"}
    )
    assert resp.status_code == 401


async def test_setup_creates_account_and_logs_in(anon_client, unconfigured):
    resp = await anon_client.post(
        "/api/v1/auth/setup", json={"username": "Alice", "password": "longenough"}
    )
    assert resp.status_code == 204

    # The account lives in the users table, normalised to lowercase.
    async with get_session_factory()() as session:
        user = (
            await session.execute(select(User).where(User.username == "alice"))
        ).scalar_one()
    assert auth.verify_password("longenough", user.password_hash)

    # Setup logs the user straight in, and a normal login works too.
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


async def test_setup_rejects_invalid_username(anon_client, unconfigured):
    resp = await anon_client.post(
        "/api/v1/auth/setup", json={"username": "bad user!", "password": "longenough"}
    )
    assert resp.status_code == 422


async def test_setup_conflicts_once_configured(anon_client):
    resp = await anon_client.post(
        "/api/v1/auth/setup", json={"username": "eve", "password": "longenough"}
    )
    assert resp.status_code == 409


async def test_setup_can_be_disabled(anon_client, unconfigured, settings, monkeypatch):
    """Hosted mode: AUTH_ALLOW_SETUP=false closes the fresh-instance race."""
    monkeypatch.setattr(settings, "auth_allow_setup", False)
    resp = await anon_client.post(
        "/api/v1/auth/setup", json={"username": "eve", "password": "longenough"}
    )
    assert resp.status_code == 403
