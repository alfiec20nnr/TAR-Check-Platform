"""Search pipeline orchestrator.

Executes the full workflow for one search job:

  connectors (concurrent) -> normalise -> deduplicate -> identity matching
  -> risk scoring -> AI summary -> report generation -> audit entry

The pipeline owns its database session and always leaves the search in a
terminal state (completed/failed).
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.connectors.base import ConnectorStatus, SearchSubject
from app.connectors.registry import get_registry
from app.database import get_session_factory
from app.models import AISummary, Report, RiskScore, Search, SearchResult, SearchStatus, Source
from app.services import audit, report_generator
from app.services.ai_summary import AiSummariser
from app.services.dedup import deduplicate
from app.services.identity_matching import IdentityMatcher
from app.services.risk_scoring import RiskScorer

logger = logging.getLogger(__name__)


async def run_search_pipeline(search_id: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    async with get_session_factory()() as session:
        search = await session.get(Search, search_id)
        if search is None:
            logger.error("Pipeline: search %s not found", search_id)
            return
        try:
            await _execute(session, search, settings)
        except Exception as exc:  # noqa: BLE001 — terminal failure recorded on the job
            logger.exception("Pipeline failed for search %s", search_id)
            search.status = SearchStatus.FAILED.value
            search.error = str(exc)
            search.completed_at = datetime.now(UTC)
            await audit.record(
                session, "search_failed", search_id=search.id, details={"error": str(exc)}
            )
            await session.commit()


async def _enabled_source_names(session: AsyncSession) -> set[str] | None:
    rows = (await session.execute(select(Source))).scalars().all()
    if not rows:
        return None  # registry not seeded — run everything
    return {r.name for r in rows if r.enabled}


async def _execute(session: AsyncSession, search: Search, settings: Settings) -> None:
    started = datetime.now(UTC)
    search.status = SearchStatus.RUNNING.value
    search.started_at = started
    await session.commit()

    subject = SearchSubject(
        full_name=search.full_name,
        date_of_birth=search.date_of_birth,
        country=search.country,
    )

    # 1. Run connectors concurrently.
    registry = get_registry(settings)
    enabled = await _enabled_source_names(session)
    connector_results = await registry.run_all(subject, enabled)
    connector_stats = [
        {
            "connector": r.connector,
            "status": r.status.value,
            "findings": len(r.findings),
            "duration_ms": r.duration_ms,
            "error": r.error,
        }
        for r in connector_results
    ]
    sources_searched = [
        r.connector for r in connector_results if r.status != ConnectorStatus.SKIPPED
    ]

    # 2-3. Normalise (already normalised by connectors) and deduplicate.
    findings = deduplicate(
        [f for r in connector_results for f in r.findings]
    )

    # 4-5. Identity matching → confidence per candidate record.
    matcher = IdentityMatcher.from_path(settings.matching_config_path)
    scored_findings = [(f, matcher.confidence(subject, f)) for f in findings]

    # 6. Risk scoring.
    scorer = RiskScorer.from_path(settings.risk_config_path)
    assessment = scorer.assess(scored_findings)

    # Persist normalised results.
    result_rows: list[SearchResult] = []
    for finding, confidence in scored_findings:
        row = SearchResult(
            search_id=search.id,
            source_name=finding.source,
            category=finding.category,
            title=finding.title,
            description=finding.description,
            url=finding.url,
            event_date=finding.date,
            subject_name=finding.subject_name,
            location=finding.location,
            confidence=confidence,
            risk_contribution=scorer.per_finding_contribution(finding, confidence),
            raw=finding.raw,
        )
        session.add(row)
        result_rows.append(row)

    session.add(
        RiskScore(
            search_id=search.id,
            score=assessment.score,
            level=assessment.level,
            factors=assessment.factors,
        )
    )

    # 7. AI summary (falls back to a template when no API key).
    summariser = AiSummariser(settings)
    summary = await summariser.summarise(subject, scored_findings)
    session.add(
        AISummary(
            search_id=search.id,
            model=summary.model,
            is_fallback=summary.is_fallback,
            content=summary.content,
        )
    )

    # 8. Generate and store the report.
    completed = datetime.now(UTC)
    duration_ms = int((completed - started).total_seconds() * 1000)
    reference = report_generator.make_reference()
    report_json = report_generator.build_report_content(
        reference=reference,
        subject={
            "full_name": search.full_name,
            "date_of_birth": search.date_of_birth,
            "country": search.country,
        },
        risk={
            "score": assessment.score,
            "level": assessment.level,
            "factors": assessment.factors,
        },
        ai={"is_fallback": summary.is_fallback, "model": summary.model,
            "content": summary.content},
        results=[
            {
                "source_name": row.source_name,
                "category": row.category,
                "title": row.title,
                "description": row.description,
                "url": row.url,
                "event_date": row.event_date,
                "confidence": row.confidence,
            }
            for row in result_rows
        ],
        sources_searched=sources_searched,
        connector_stats=connector_stats,
        duration_ms=duration_ms,
    )
    html = report_generator.render_html(report_json)
    session.add(
        Report(
            search_id=search.id,
            reference=reference,
            json_content=report_json,
            html_content=html,
        )
    )

    # Finalise the search row (denormalised dashboard fields included).
    search.status = SearchStatus.COMPLETED.value
    search.completed_at = completed
    search.duration_ms = duration_ms
    search.results_count = len(result_rows)
    search.risk_score_value = assessment.score
    search.risk_level = assessment.level
    search.sources_searched = sources_searched

    # 9. Append-only audit entry.
    await audit.record(
        session,
        "search_completed",
        search_id=search.id,
        details={
            "sources_searched": sources_searched,
            "duration_ms": duration_ms,
            "results_found": len(result_rows),
            "risk_level": assessment.level,
            "report_reference": reference,
            "connector_stats": connector_stats,
        },
    )
    await session.commit()
    logger.info(
        "Search %s completed: %d results, risk %s (%s)",
        search.id, len(result_rows), assessment.score, assessment.level,
    )
