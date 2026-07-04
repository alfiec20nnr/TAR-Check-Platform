"""Dashboard, sources registry, and audit read endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AuditLog, Search, SearchStatus, Source
from app.schemas import AuditEntryOut, DashboardStats, SearchOut, SourceOut

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/stats", response_model=DashboardStats)
async def dashboard_stats(db: AsyncSession = Depends(get_db)) -> DashboardStats:
    async def count(*conditions) -> int:
        q = select(func.count()).select_from(Search)
        for cond in conditions:
            q = q.where(cond)
        return (await db.execute(q)).scalar_one()

    recent = (
        (await db.execute(select(Search).order_by(Search.created_at.desc()).limit(10)))
        .scalars()
        .all()
    )
    high_risk = (
        (
            await db.execute(
                select(Search)
                .where(Search.risk_level.in_(["high", "critical"]))
                .order_by(Search.created_at.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    return DashboardStats(
        total_searches=await count(),
        running_searches=await count(
            Search.status.in_([SearchStatus.PENDING.value, SearchStatus.RUNNING.value])
        ),
        completed_searches=await count(Search.status == SearchStatus.COMPLETED.value),
        failed_searches=await count(Search.status == SearchStatus.FAILED.value),
        high_risk_searches=await count(Search.risk_level.in_(["high", "critical"])),
        recent_searches=[SearchOut.model_validate(s) for s in recent],
        high_risk_recent=[SearchOut.model_validate(s) for s in high_risk],
    )


@router.get("/sources", response_model=list[SourceOut])
async def list_sources(db: AsyncSession = Depends(get_db)) -> list[Source]:
    return (await db.execute(select(Source).order_by(Source.name))).scalars().all()


@router.get("/audit", response_model=list[AuditEntryOut])
async def list_audit_entries(
    db: AsyncSession = Depends(get_db),
    search_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> list[AuditLog]:
    """Read-only view of the append-only audit log."""
    q = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    if search_id:
        q = q.where(AuditLog.search_id == search_id)
    return (await db.execute(q)).scalars().all()
