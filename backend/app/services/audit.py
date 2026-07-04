"""Search History & Audit Module — append-only audit writes."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def record(
    session: AsyncSession,
    action: str,
    search_id: str | None = None,
    details: dict | None = None,
) -> AuditLog:
    """Append an audit entry. Entries are never updated or deleted."""
    entry = AuditLog(search_id=search_id, action=action, details=details)
    session.add(entry)
    await session.flush()
    return entry
