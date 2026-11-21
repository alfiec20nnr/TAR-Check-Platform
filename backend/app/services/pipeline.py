"""Search pipeline orchestrator.

Executes the full workflow for one search job:

  connectors (concurrent, in priority order) -> normalise -> deduplicate
  -> adverse-keyword screening (all sources) -> identity matching
  -> risk scoring -> AI summary -> report generation -> audit entry

The pipeline owns its database session and always leaves the search in a
terminal state (completed/failed).
"""

import asyncio
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
from app.services.keyword_screening import KeywordScreener
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


# Share of the progress bar given to the connector stage (the slow part);
# the remaining stages are quick and fill the rest.
_CONNECTOR_PROGRESS_START = 5
_CONNECTOR_PROGRESS_END = 75


async def _set_progress(
    session: AsyncSession, search: Search, percent: int, stage: str
) -> None:
    search.progress = max(search.progress or 0, min(percent, 100))
    search.progress_stage = stage
    await session.commit()


async def _execute(session: AsyncSession, search: Search, settings: Settings) -> None:
    started = datetime.now(UTC)
    search.status = SearchStatus.RUNNING.value
    search.started_at = started
    await _set_progress(session, search, _CONNECTOR_PROGRESS_START, "Querying data sources")

    subject = SearchSubject(
        full_name=search.full_name,
        date_of_birth=search.date_of_birth,
        # The platform screens UK individuals: no country means the UK.
        country=search.country or settings.default_country or None,
        location=search.location,
        driving_licence_number=search.driving_licence_number,
    )

    # 1. Run connectors concurrently.
    registry = get_registry(settings)
    enabled = await _enabled_source_names(session)
    # Connectors finish concurrently; serialise the progress commits because
    # an AsyncSession must not be used by two tasks at once.
    progress_lock = asyncio.Lock()

    async def on_connector_done(done: int, total: int, name: str) -> None:
        span = _CONNECTOR_PROGRESS_END - _CONNECTOR_PROGRESS_START
        percent = _CONNECTOR_PROGRESS_START + int(span * done / max(total, 1))
        async with progress_lock:
            await _set_progress(
                session, search, percent, f"Querying data sources ({done}/{total})"
            )

    connector_results = await registry.run_all(subject, enabled, on_connector_done)
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
    # Results arrive in connector priority order, so when the same record is
    # returned by several sources the highest-priority source's copy is kept.
    findings = deduplicate(
        [f for r in connector_results for f in r.findings]
    )

    await _set_progress(session, search, 78, "Screening and matching identities")

    # 3b. Screen every finding from every source against the broad adverse
    # keyword list. Flags and re-categorises; never discards.
    screener = KeywordScreener.from_path(settings.adverse_keywords_path)
    flagged_count = sum(1 for f in findings if screener.flag(f))

    # 4-5. Identity matching → confidence per candidate record.
    matcher = IdentityMatcher.from_path(settings.matching_config_path)
    # Record date-of-birth evidence found in record text (formal records,
    # court/police reports) so the report can show what verified the match.
    for f in findings:
        evidence = matcher.text_dob_evidence(subject, f)
        if evidence.status:
            f.raw = {**(f.raw or {}), "dob_check": evidence.status,
                     "dob_check_detail": evidence.detail}
    scored_findings = [(f, matcher.confidence(subject, f)) for f in findings]
    # Discard records that are not the person searched for (conflicting
    # forename, different date of birth) — they are never stored or reported.
    discarded_count = sum(1 for _, c in scored_findings if not matcher.is_subject(c))
    scored_findings = [(f, c) for f, c in scored_findings if matcher.is_subject(c)]

    # 6. Risk scoring.
    scorer = RiskScorer.from_path(settings.risk_config_path, settings.adverse_keywords_path)
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

    await _set_progress(session, search, 82, "Generating AI summary")

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

    await _set_progress(session, search, 92, "Generating report")

    # 8. Generate and store the report.
    completed = datetime.now(UTC)
    duration_ms = int((completed - started).total_seconds() * 1000)
    reference = report_generator.make_reference()
    report_json = report_generator.build_report_content(
        reference=reference,
        mock_mode=settings.mock_connectors,
        subject={
            "full_name": search.full_name,
            "date_of_birth": search.date_of_birth,
            "country": search.country,
            "location": search.location,
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
                "flagged_terms": (row.raw or {}).get("flagged_terms", []),
                "dob_check": (row.raw or {}).get("dob_check"),
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
    search.progress = 100
    search.progress_stage = "Complete"
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
            "results_discarded": discarded_count,
            "results_flagged": flagged_count,
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
