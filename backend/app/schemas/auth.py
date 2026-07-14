"""Schemas for the single-user login endpoints."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class SetupRequest(BaseModel):
    """First-launch credential creation (only valid while no password is set)."""

    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)


class AuthStatus(BaseModel):
    configured: bool  # False until first-launch setup has chosen a password
    authenticated: bool
