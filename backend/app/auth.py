"""Single-user login: password hashing, signed session cookies, route guard.

Deliberately minimal for a single-device deployment — one username/password
pair stored (hashed) in `.env`, no users table, no roles. Sessions are a
stateless HMAC-signed expiry cookie, so nothing is persisted server-side and
no new dependencies are needed: hashing uses stdlib PBKDF2, signing uses
stdlib HMAC with the AUTH_SECRET that app.ensure_key generates into `.env`.

This is a lock screen for the machine the app runs on (the server binds to
localhost), not network-facing security.
"""

import base64
import hashlib
import hmac
import logging
import secrets
import time

from fastapi import HTTPException, Request, Response, status

from app import licensing
from app.config import get_settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "aip_session"

_PBKDF2_ITERATIONS = 600_000

# Fallback when AUTH_SECRET is missing (e.g. a Docker stack that never ran
# app.ensure_key): sessions still work but do not survive a restart.
_ephemeral_secret: str | None = None


def hash_password(password: str, iterations: int = _PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.urlsafe_b64encode(salt).decode(),
        base64.urlsafe_b64encode(digest).decode(),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64)
        expected = base64.urlsafe_b64decode(digest_b64)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
    return hmac.compare_digest(actual, expected)


def _secret() -> str:
    global _ephemeral_secret
    secret = get_settings().auth_secret
    if secret:
        return secret
    if _ephemeral_secret is None:
        _ephemeral_secret = secrets.token_urlsafe(32)
        logger.warning(
            "AUTH_SECRET is not set — using an ephemeral signing key; "
            "logins will not survive a server restart."
        )
    return _ephemeral_secret


def _sign(payload: str) -> str:
    digest = hmac.new(_secret().encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def create_session_token() -> str:
    expires_at = int(time.time()) + get_settings().auth_session_hours * 3600
    payload = f"aip-session:{expires_at}"
    return f"{expires_at}.{_sign(payload)}"


def verify_session_token(token: str) -> bool:
    expires_at, _, signature = token.partition(".")
    if not expires_at.isdigit() or not signature:
        return False
    if not hmac.compare_digest(_sign(f"aip-session:{expires_at}"), signature):
        return False
    return int(expires_at) > time.time()


def set_session_cookie(response: Response) -> None:
    response.set_cookie(
        COOKIE_NAME,
        create_session_token(),
        max_age=get_settings().auth_session_hours * 3600,
        httponly=True,
        samesite="strict",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


def is_authenticated(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME)
    return bool(token) and verify_session_token(token)


def require_activation() -> None:
    """Reject requests until this machine has a valid activation code."""
    if not licensing.is_activated():
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Activation required")


def require_auth(request: Request) -> None:
    """Router dependency: reject requests without a valid session cookie."""
    require_activation()
    if not get_settings().auth_password_hash:
        # First launch — nothing to log in with yet; the UI shows the setup
        # form when it sees this detail string.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Initial setup required"
        )
    if not is_authenticated(request):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
