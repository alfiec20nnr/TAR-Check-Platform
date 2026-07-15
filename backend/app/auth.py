"""Login: password hashing, signed session cookies, route guard.

Accounts live in the users table (see app.models.user) — one row per person
on a hosted instance, a single auto-seeded row on a local install. All
accounts are equal; there are no roles.

Sessions are a stateless HMAC-signed cookie carrying the username and an
expiry, so nothing is persisted server-side and no new dependencies are
needed: hashing uses stdlib PBKDF2, signing uses stdlib HMAC with the
AUTH_SECRET that app.ensure_key generates into `.env`. The route guard also
confirms on every request that the user still exists and is active, so
removing or disabling an account revokes its sessions immediately.
"""

import base64
import hashlib
import hmac
import logging
import secrets
import time

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import licensing
from app.config import get_settings
from app.database import get_db
from app.models.user import User, normalise_username

logger = logging.getLogger(__name__)

COOKIE_NAME = "aip_session"

_PBKDF2_ITERATIONS = 600_000

# Fallback when AUTH_SECRET is missing (e.g. a Docker stack that never ran
# app.ensure_key): sessions still work but do not survive a restart.
_ephemeral_secret: str | None = None


def hash_password(password: str, iterations: int = _PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    salt_b64 = base64.urlsafe_b64encode(salt).decode()
    digest_b64 = base64.urlsafe_b64encode(digest).decode()
    return f"pbkdf2_sha256${iterations}${salt_b64}${digest_b64}"


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


def _b64encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _b64decode(value: str) -> str | None:
    try:
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded).decode()
    except (ValueError, UnicodeDecodeError):
        return None


def create_session_token(username: str) -> str:
    expires_at = int(time.time()) + get_settings().auth_session_hours * 3600
    payload = f"aip-session:{username}:{expires_at}"
    return f"{_b64encode(username)}.{expires_at}.{_sign(payload)}"


def verify_session_token(token: str) -> str | None:
    """Return the username of a valid, unexpired token; None otherwise.

    Pre-multi-user tokens (``{expires}.{sig}``, no username) fail the
    three-part split and are rejected — holders just log in again once.
    """
    parts = token.split(".")
    if len(parts) != 3:
        return None
    username_b64, expires_at, signature = parts
    if not expires_at.isdigit() or not signature:
        return None
    username = _b64decode(username_b64)
    if not username:
        return None
    payload = f"aip-session:{username}:{expires_at}"
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    if int(expires_at) <= time.time():
        return None
    return username


def set_session_cookie(response: Response, username: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        create_session_token(username),
        max_age=get_settings().auth_session_hours * 3600,
        httponly=True,
        samesite="strict",
        secure=get_settings().session_cookie_secure,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


def session_username(request: Request) -> str | None:
    """Username from a validly signed session cookie (no DB check)."""
    token = request.cookies.get(COOKIE_NAME)
    return verify_session_token(token) if token else None


def require_activation() -> None:
    """Reject requests until this machine has a valid activation code."""
    if not licensing.is_activated():
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Activation required")


async def any_user_exists(db: AsyncSession) -> bool:
    return (await db.execute(select(User.id).limit(1))).first() is not None


async def get_active_user(db: AsyncSession, username: str) -> User | None:
    """The active account for *username* (normalised), or None."""
    user = (
        await db.execute(
            select(User).where(User.username == normalise_username(username))
        )
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


async def require_auth(
    request: Request, db: AsyncSession = Depends(get_db)
) -> str:
    """Router/handler dependency: valid session for an existing active user.

    Returns the username so handlers that record the actor can depend on this
    directly (FastAPI runs a dependency once per request, so router-level and
    handler-level uses share the same DB check).
    """
    require_activation()
    username = session_username(request)
    if username is not None:
        user = await get_active_user(db, username)
        if user is not None:
            return user.username
    if not await any_user_exists(db):
        # First launch — nothing to log in with yet; the UI shows the setup
        # form when it sees this detail string.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Initial setup required"
        )
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
