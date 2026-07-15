"""Login accounts.

Every deployment uses the same users table: a hosted instance holds one row
per person (created with `python -m app.users`), while a local single-user
install gets a single row seeded automatically from the legacy `.env`
credentials on first start after upgrading (see app.seed.seed_default_user).
All accounts are equal — there are no roles or permissions.
"""

import re
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.search import utcnow

# Enforced when accounts are created (setup endpoint / CLI). Lowercase only —
# usernames are normalised before lookup so logins are case-insensitive.
USERNAME_RE = re.compile(r"^[a-z0-9._@-]{3,100}$")


def _uuid() -> str:
    return str(uuid.uuid4())


def normalise_username(username: str) -> str:
    return username.strip().lower()


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    # Disabled accounts keep their history but cannot log in, and any live
    # session is rejected on its next request.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
