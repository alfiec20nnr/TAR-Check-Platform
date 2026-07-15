"""Search endpoints: submit, status, results, history (incl. deletion)."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import require_auth
from app.config import get_settings
from app.database import get_db
from app.models import AISummary, Report, RiskScore, Search, SearchResult, SearchStatus
from app.schemas import PaginatedSearches, SearchCreate, SearchDetail, SearchOut
from app.services import audit
from app.services.pipeline import run_search_pipeline

_TERMINAL = (SearchStatus.COMPLETED.value, SearchStatus.FAILED.value)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/searches", tags=["searches"])


@router.post("", response_model=SearchOut, status_code=202)
async def submit_search(
    payload: SearchCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    username: str = Depends(require_auth),
) -> Search:
    """Submit a search; returns immediately with the search ID.

    The pipeline runs in the background (dedicated worker container, or an
    in-process task when INLINE_WORKER is enabled for development).
    """
    settings = get_settings()
    search = Search(
        full_name=payload.full_name,
        date_of_birth=payload.date_of_birth.isoformat() if payload.date_of_birth else None,
        country=payload.country,
        driving_licence_number=payload.driving_licence_number,
        status=SearchStatus.PENDING.value,
        created_by=username,
    )
    db.add(search)
    await db.flush()  # populate search.id before the audit entry references it
    await audit.record(
        db,
        "search_submitted",
        search_id=search.id,
        actor=username,
        details={
            "country": payload.country,
            "dob_provided": payload.date_of_birth is not None,
            # The licence number itself is never audited — only the fact a
            # consented DVLA check was requested.
            "licence_check_requested": payload.driving_licence_number is not None,
            "licence_check_consent": payload.licence_check_consent,
        },
    )
    await db.commit()
    await db.refresh(search)

    if settings.inline_worker:
        # Fire-and-forget inside the API process; the worker container is the
        # production path.
        asyncio.get_running_loop().create_task(run_search_pipeline(search.id, settings))

    return search


@router.get("", response_model=PaginatedSearches)
async def list_searches(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    risk_level: str | None = Query(None),
) -> PaginatedSearches:
    """Paginated, filterable search history (append-only)."""
    query = select(Search)
    if status:
        query = query.where(Search.status == status)
    if risk_level:
        query = query.where(Search.risk_level == risk_level)

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                query.order_by(Search.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return PaginatedSearches(
        items=[SearchOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


async def _delete_search_rows(db: AsyncSession, search_ids: list[str]) -> None:
    """Remove searches and their dependent rows.

    Children are deleted explicitly (rather than relying on DB-level ON DELETE
    CASCADE) so behaviour is identical on PostgreSQL and SQLite. Audit-log
    entries are never touched — the record *that a search happened* is
    append-only and permanent.
    """
    if not search_ids:
        return
    for model in (SearchResult, Report, AISummary, RiskScore):
        await db.execute(delete(model).where(model.search_id.in_(search_ids)))
    await db.execute(delete(Search).where(Search.id.in_(search_ids)))


@router.delete("", status_code=200)
async def clear_history(
    db: AsyncSession = Depends(get_db), username: str = Depends(require_auth)
) -> dict:
    """Clear the search history (completed/failed searches only).

    In-flight searches are left untouched; audit entries are always retained,
    and the clearance itself is audited.
    """
    ids = list(
        (
            await db.execute(select(Search.id).where(Search.status.in_(_TERMINAL)))
        ).scalars()
    )
    await _delete_search_rows(db, ids)
    await audit.record(
        db, "history_cleared", actor=username, details={"deleted": len(ids)}
    )
    await db.commit()
    return {"deleted": len(ids)}


@router.delete("/{search_id}", status_code=204)
async def delete_search(
    search_id: str,
    db: AsyncSession = Depends(get_db),
    username: str = Depends(require_auth),
) -> None:
    """Delete a single search from the history (with its results and report)."""
    search = await db.get(Search, search_id)
    if search is None:
        raise HTTPException(status_code=404, detail="Search not found")
    if search.status not in _TERMINAL:
        raise HTTPException(
            status_code=409,
            detail="Search is still running — wait for it to finish before deleting",
        )
    await _delete_search_rows(db, [search_id])
    await audit.record(db, "search_deleted", search_id=search_id, actor=username)
    await db.commit()


@router.get("/{search_id}", response_model=SearchDetail)
async def get_search(search_id: str, db: AsyncSession = Depends(get_db)) -> SearchDetail:
    """Search status plus normalised results (poll until status is terminal)."""
    result = await db.execute(
        select(Search).options(selectinload(Search.results)).where(Search.id == search_id)
    )
    search = result.scalar_one_or_none()
    if search is None:
        raise HTTPException(status_code=404, detail="Search not found")

    report_ref = (
        await db.execute(select(Report.reference).where(Report.search_id == search_id))
    ).scalar_one_or_none()

    detail = SearchDetail.model_validate(search)
    detail.report_reference = report_ref
    return detail
