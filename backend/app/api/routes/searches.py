"""Search endpoints: submit, status, results, history."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.models import Report, Search, SearchStatus
from app.schemas import PaginatedSearches, SearchCreate, SearchDetail, SearchOut
from app.services import audit
from app.services.pipeline import run_search_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/searches", tags=["searches"])


@router.post("", response_model=SearchOut, status_code=202)
async def submit_search(
    payload: SearchCreate, request: Request, db: AsyncSession = Depends(get_db)
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
    )
    db.add(search)
    await db.flush()  # populate search.id before the audit entry references it
    await audit.record(
        db,
        "search_submitted",
        search_id=search.id,
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
