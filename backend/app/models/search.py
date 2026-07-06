"""Search job and normalised search-result records."""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.security import EncryptedString


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class SearchStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Search(Base):
    __tablename__ = "searches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Personal data is encrypted at rest (see app.security.EncryptedString).
    full_name: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    date_of_birth: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Optional — enables the DVLA licence check. Encrypted: the number itself
    # encodes the holder's name and date of birth.
    driving_licence_number: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), default=SearchStatus.PENDING.value, nullable=False, index=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Denormalised for dashboard/history queries.
    results_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    risk_score_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    sources_searched: Mapped[list | None] = mapped_column(JSON, nullable=True)

    results: Mapped[list["SearchResult"]] = relationship(
        back_populates="search", cascade="all, delete-orphan"
    )


class SearchResult(Base):
    __tablename__ = "search_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    search_id: Mapped[str] = mapped_column(
        ForeignKey("searches.id", ondelete="CASCADE"), nullable=False, index=True
    )

    source_name: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    subject_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)

    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    risk_contribution: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    search: Mapped[Search] = relationship(back_populates="results")
