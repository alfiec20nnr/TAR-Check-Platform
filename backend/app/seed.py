"""Seed the connector registry (Sources table).

Idempotent — safe to run on every container start:  python -m app.seed
"""

import asyncio
import logging

from sqlalchemy import select

from app.connectors.registry import get_registry
from app.database import get_session_factory
from app.models import Source

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_sources())
