"""Seed the connector registry (Sources table) and the default user.

Idempotent — safe to run on every container start:  python -m app.seed
"""

import asyncio
import logging

from sqlalchemy import select

from app.config import get_settings
from app.connectors.registry import get_registry
from app.database import get_session_factory
from app.models import Source, User
from app.models.user import normalise_username

logger = logging.getLogger(__name__)


async def seed_sources() -> None:
    registry = get_registry()
    async with get_session_factory()() as session:
        existing = {
            s.name for s in (await session.execute(select(Source))).scalars().all()
        }
        added = 0
        for meta in registry.list_metadata():
            if meta["name"] in existing:
                continue
            session.add(
                Source(
                    name=meta["name"],
                    display_name=meta["display_name"],
                    description=meta["description"],
                    enabled=True,
                )
            )
            added += 1
        await session.commit()
        logger.info("Seeded %d source(s)", added)


async def seed_default_user() -> None:
    """Migrate a pre-multi-user install's `.env` login into the users table.

    Runs on every start but only acts when the users table is empty and the
    legacy AUTH_USERNAME/AUTH_PASSWORD_HASH pair is set — i.e. exactly once,
    the first start after upgrading. The user keeps the same credentials.
    Fresh installs (no legacy hash) are untouched: the first-launch setup
    screen creates user #1 instead.
    """
    settings = get_settings()
    if not settings.auth_password_hash:
        return
    async with get_session_factory()() as session:
        if (await session.execute(select(User.id).limit(1))).first() is not None:
            return
        username = normalise_username(settings.auth_username) or "admin"
        session.add(
            User(username=username, password_hash=settings.auth_password_hash)
        )
        await session.commit()
        logger.info(
            "Migrated login credentials from .env into the users table "
            "for user %r",
            username,
        )


async def seed_all() -> None:
    await seed_sources()
    await seed_default_user()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_all())
