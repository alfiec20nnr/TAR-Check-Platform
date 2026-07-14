"""Schemas for the machine-activation endpoints."""

from pydantic import BaseModel, Field


class LicenceStatus(BaseModel):
    activated: bool
    machine_code: str  # shown to the user so they can request an activation code


class ActivateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=500)
