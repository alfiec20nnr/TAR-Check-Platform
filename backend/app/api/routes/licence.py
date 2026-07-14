"""Machine-activation endpoints (see app.licensing).

Open (no session cookie needed): the activation screen is what an unactivated
machine shows before anything else, including login.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, status

from app import licensing
from app.config import get_settings
from app.ensure_key import set_env_var
from app.schemas import ActivateRequest, LicenceStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/licence", tags=["licence"])

_FAILED_ATTEMPT_DELAY_SECONDS = 0.5


@router.get("/status", response_model=LicenceStatus)
async def licence_status() -> LicenceStatus:
    return LicenceStatus(
        activated=licensing.is_activated(), machine_code=licensing.machine_code()
    )


@router.post("/activate", status_code=204)
async def activate(payload: ActivateRequest) -> None:
    code = licensing.normalise(payload.code)
    if not licensing.verify_activation_code(code):
        await asyncio.sleep(_FAILED_ATTEMPT_DELAY_SECONDS)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="That activation code is not valid for this machine.",
        )
    try:
        set_env_var(
            "LICENCE_KEY",
            code,
            comment=["Machine activation code — valid for this machine only."],
        )
    except OSError:
        logger.exception(
            "Could not persist LICENCE_KEY to .env — activation will apply "
            "for this run only."
        )
    get_settings().licence_key = code
    licensing.reset_cache()
    logger.info("Machine activated (machine code %s)", licensing.machine_code())
