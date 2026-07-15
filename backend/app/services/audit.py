"""Search History & Audit Module — append-only audit writes."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def record(
    session: AsyncSession,
    action: str,
    search_id: str | None = None,
    details: dict | None = None,
    actor: str | None = None,
) -> AuditLog:
    """Append an audit entry. Entries are never updated or deleted.

    *actor* is the username that performed the action; None for actions the
    system takes by itself (pipeline stages, retention, crash recovery).
    """
    entry = AuditLog(search_id=search_id, action=action, details=details, actor=actor)
    session.add(entry)
    await session.flush()
    return entry
