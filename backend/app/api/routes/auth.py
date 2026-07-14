"""Login endpoints for the single-user lock screen.

These are the only API routes (besides /health and the session-presence
beacons) that do not require a session cookie.
"""

import asyncio
import hmac
import logging

from fastapi import APIRouter, HTTPException, Request, Response, status

from app import auth
from app.config import get_settings
from app.ensure_key import set_env_var
from app.schemas import AuthStatus, LoginRequest, SetupRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Flat delay on every failed login. Combined with the global per-IP rate
# limit this is plenty to blunt brute force on a localhost lock screen.
_FAILED_LOGIN_DELAY_SECONDS = 0.5


@router.get("/status", response_model=AuthStatus)
async def auth_status(request: Request) -> AuthStatus:
    settings = get_settings()
    return AuthStatus(
        configured=bool(settings.auth_password_hash),
        authenticated=bool(settings.auth_password_hash)
        and auth.is_authenticated(request),
    )


@router.post("/setup", status_code=204)
async def setup(payload: SetupRequest, response: Response) -> None:
    """First-launch credential creation; persists to `.env` and logs in."""
    settings = get_settings()
    if settings.auth_password_hash:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Credentials are already configured."
        )
    password_hash = auth.hash_password(payload.password)
    try:
        set_env_var("AUTH_USERNAME", payload.username)
        set_env_var(
            "AUTH_PASSWORD_HASH",
            password_hash,
            comment=["Login credentials — change with: python -m app.set_password"],
        )
    except OSError:
        # e.g. read-only container filesystem: credentials still apply for
        # this run so the user is not locked out, but will be asked again.
        logger.exception(
            "Could not persist credentials to .env — they will apply "
            "for this run only."
        )
    settings.auth_username = payload.username
    settings.auth_password_hash = password_hash
    auth.set_session_cookie(response)
    logger.info("Login credentials created for user %r", payload.username)


@router.post("/login", status_code=204)
async def login(payload: LoginRequest, response: Response) -> None:
    settings = get_settings()
    if not settings.auth_password_hash:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Initial setup required"
        )
    username_ok = hmac.compare_digest(
        payload.username.encode(), settings.auth_username.encode()
    )
    password_ok = auth.verify_password(payload.password, settings.auth_password_hash)
    if not (username_ok and password_ok):
        await asyncio.sleep(_FAILED_LOGIN_DELAY_SECONDS)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password."
        )
    auth.set_session_cookie(response)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    auth.clear_session_cookie(response)
