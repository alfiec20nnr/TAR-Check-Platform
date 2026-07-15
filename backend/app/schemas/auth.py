"""Schemas for the login endpoints."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class SetupRequest(BaseModel):
    """First-launch account creation (only valid while no user exists)."""

    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class AuthStatus(BaseModel):
    configured: bool  # False until the first account exists
    authenticated: bool
    username: str | None = None  # the logged-in user, when authenticated
