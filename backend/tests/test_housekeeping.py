"""Single-process startup housekeeping (app.main._single_process_housekeeping).

In no-Docker mode the API process itself must recover searches interrupted by
a shutdown (they can never finish — and would block auto-shutdown forever)
and apply the data-retention policy the Docker worker normally handles.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.database import get_session_factory
from app.main import _single_process_housekeeping
from app.models import AuditLog, Report, Search, SearchResult, SearchStatus
from app.services import audit


async def test_interrupted_searches_are_failed():
    factory = get_session_factory()
    async with factory() as session:
        running = Search(full_name="Interrupted Runner", status=SearchStatus.RUNNING.value)
        pending = Search(full_name="Interrupted Pending", status=SearchStatus.PENDING.value)
        completed = Search(full_name="Finished Fine", status=SearchStatus.COMPLETED.value)
        session.add_all([running, pending, completed])
        await session.commit()
        ids = (running.id, pending.id, completed.id)

    await _single_process_housekeeping()

    async with factory() as session:
        for search_id in ids[:2]:
            row = await session.get(Search, search_id)
            assert row.status == SearchStatus.FAILED.value
            assert "Interrupted" in row.error
            assert row.completed_at is not None
        untouched = await session.get(Search, ids[2])
        assert untouched.status == SearchStatus.COMPLETED.value

        failures = (
            (
                await session.execute(
                    select(AuditLog).where(AuditLog.action == "search_failed")
                )
            )
            .scalars()
            .all()
        )
        assert len(failures) == 2


async def test_retention_removes_expired_searches_but_keeps_audit():
    factory = get_session_factory()
    expired_date = datetime.now(UTC) - timedelta(days=400)  # default retention 365
    async with factory() as session:
        expired = Search(
            full_name="Long Gone",
            status=SearchStatus.COMPLETED.value,
            created_at=expired_date,
        )
        recent = Search(full_name="Still Fresh", status=SearchStatus.COMPLETED.value)
        session.add_all([expired, recent])
        await session.flush()
        session.add(
            SearchResult(
                search_id=expired.id,
                source_name="mock",
                category="adverse_media",
                title="Old finding",
            )
        )
        session.add(
            Report(
                search_id=expired.id,
                reference="AIP-TEST-RET",
                json_content={},
                html_content="<html></html>",
            )
        )
        await audit.record(session, "search_completed", search_id=expired.id)
        await session.commit()
        expired_id, recent_id = expired.id, recent.id

    await _single_process_housekeeping()

    async with factory() as session:
        assert await session.get(Search, expired_id) is None
        assert await session.get(Search, recent_id) is not None

        # Children were deleted explicitly (SQLite has no cascade by default).
        orphan_results = (
            await session.execute(select(func.count()).select_from(SearchResult))
        ).scalar_one()
        orphan_reports = (
            await session.execute(select(func.count()).select_from(Report))
        ).scalar_one()
        assert orphan_results == 0
        assert orphan_reports == 0

        # The append-only audit trail survives, including a retention entry.
        actions = set(
            (await session.execute(select(AuditLog.action))).scalars().all()
        )
        assert "search_completed" in actions
        assert "retention_applied" in actions
