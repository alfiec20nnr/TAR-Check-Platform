"""Login endpoints.

These are the only API routes (besides /health, licence activation, and the
session-presence beacons) that do not require a session cookie — except
change-password, which does.
"""

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import auth
from app.config import get_settings
from app.database import get_db
from app.models.user import USERNAME_RE, User, normalise_username
from app.rate_limit import limiter
from app.schemas import (
    AuthStatus,
    ChangePasswordRequest,
    LoginRequest,
    SetupRequest,
)
from app.services import audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Flat delay on every failed login. Combined with the per-IP rate limits this
# is plenty to blunt brute force.
_FAILED_LOGIN_DELAY_SECONDS = 0.5


@router.get("/status", response_model=AuthStatus)
async def auth_status(
    request: Request, db: AsyncSession = Depends(get_db)
) -> AuthStatus:
    configured = await auth.any_user_exists(db)
    username = auth.session_username(request) if configured else None
    if username is not None:
        user = await auth.get_active_user(db, username)
        username = user.username if user is not None else None
    return AuthStatus(
        configured=configured,
        authenticated=username is not None,
        username=username,
    )


@router.post("/setup", status_code=204)
async def setup(
    payload: SetupRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> None:
    """First-launch account creation (local installs); creates user #1.

    Hosted deployments disable this with AUTH_ALLOW_SETUP=false and seed
    accounts with `python -m app.users` instead.
    """
    auth.require_activation()
    if not get_settings().auth_allow_setup:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Setup is disabled on this deployment."
        )
    if await auth.any_user_exists(db):
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Credentials are already configured."
        )
    username = normalise_username(payload.username)
    if not USERNAME_RE.fullmatch(username):
        raise HTTPException(
            422,
            detail=(
                "Username must be 3-100 characters using letters, digits, "
                "dots, dashes, underscores or @."
            ),
        )
    db.add(User(username=username, password_hash=auth.hash_password(payload.password)))
    await db.commit()
    auth.set_session_cookie(response, username)
    logger.info("Login credentials created for user %r", username)


@router.post("/login", status_code=204)
@limiter.limit(lambda: get_settings().auth_login_rate_limit)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> None:
    auth.require_activation()
    if not await auth.any_user_exists(db):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Initial setup required"
        )
    username = normalise_username(payload.username)
    user = await auth.get_active_user(db, username)
    if user is None or not auth.verify_password(payload.password, user.password_hash):
        await audit.record(db, "login_failed", details={"username": username})
        await db.commit()
        await asyncio.sleep(_FAILED_LOGIN_DELAY_SECONDS)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password."
        )
    user.last_login_at = datetime.now(UTC)
    await audit.record(db, "login_succeeded", actor=user.username)
    await db.commit()
    auth.set_session_cookie(response, user.username)


@router.post("/change-password", status_code=204)
async def change_password(
    payload: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    username: str = Depends(auth.require_auth),
) -> None:
    """Self-service password change for the logged-in user."""
    user = await auth.get_active_user(db, username)
    if user is None or not auth.verify_password(
        payload.current_password, user.password_hash
    ):
        await asyncio.sleep(_FAILED_LOGIN_DELAY_SECONDS)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect."
        )
    user.password_hash = auth.hash_password(payload.new_password)
    await audit.record(db, "password_changed", actor=user.username)
    await db.commit()


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    auth.clear_session_cookie(response)
