"""Background worker.

Polls the searches table for pending jobs and runs the pipeline. Uses
``FOR UPDATE SKIP LOCKED`` so multiple workers can run safely against the same
PostgreSQL database. Also enforces the configurable data-retention policy
(audit logs are never deleted).

Run with:  python -m app.worker
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.config import get_settings
from app.database import get_session_factory
from app.models import Search, SearchStatus
from app.services.pipeline import run_search_pipeline

logger = logging.getLogger(__name__)

_RETENTION_CHECK_INTERVAL = timedelta(hours=6)


async def claim_next_search() -> str | None:
    """Atomically claim the oldest pending search, or return None."""
    async with get_session_factory()() as session:
        result = await session.execute(
            select(Search)
            .where(Search.status == SearchStatus.PENDING.value)
            .order_by(Search.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        search = result.scalar_one_or_none()
        if search is None:
            return None
        search.status = SearchStatus.RUNNING.value
        search.started_at = datetime.now(UTC)
        await session.commit()
        return search.id


async def apply_retention_policy() -> int:
    """Delete searches (and cascaded results/reports) past the retention window.

    Audit logs are intentionally retained — the history of *that a search
    happened* is append-only and permanent.
    """
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(days=settings.data_retention_days)
    async with get_session_factory()() as session:
        result = await session.execute(
            delete(Search).where(
                Search.created_at < cutoff,
                Search.status.in_(
                    [SearchStatus.COMPLETED.value, SearchStatus.FAILED.value]
                ),
            )
        )
        await session.commit()
        if result.rowcount:
            logger.info("Retention policy removed %d search(es)", result.rowcount)
        return result.rowcount or 0


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    logger.info("Worker started (poll interval %.1fs)", settings.worker_poll_interval_seconds)
    last_retention = datetime.min.replace(tzinfo=UTC)

    while True:
        try:
            search_id = await claim_next_search()
            if search_id:
                logger.info("Claimed search %s", search_id)
                await run_search_pipeline(search_id, settings)
                continue  # immediately look for more work

            now = datetime.now(UTC)
            if now - last_retention > _RETENTION_CHECK_INTERVAL:
                await apply_retention_policy()
                last_retention = now
        except Exception:  # noqa: BLE001 — the worker must never die
            logger.exception("Worker loop error")
        await asyncio.sleep(settings.worker_poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
