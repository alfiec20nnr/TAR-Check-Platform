"""Pydantic schemas for the public REST API."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SearchCreate(BaseModel):
    """Search input — deliberately minimal (data minimisation)."""

    full_name: str = Field(min_length=2, max_length=200, description="Full name (required)")
    date_of_birth: date | None = Field(default=None, description="Date of birth (optional)")
    country: str | None = Field(default=None, max_length=64, description="Country (optional)")

    @field_validator("full_name")
    @classmethod
    def name_must_have_letters(cls, v: str) -> str:
        v = " ".join(v.split())
        if not any(c.isalpha() for c in v):
            raise ValueError("full_name must contain letters")
        return v

    @field_validator("country")
    @classmethod
    def normalise_country(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None

    @field_validator("date_of_birth")
    @classmethod
    def dob_not_in_future(cls, v: date | None) -> date | None:
        if v is not None and v > date.today():
            raise ValueError("date_of_birth cannot be in the future")
        return v


class SearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    date_of_birth: str | None = None
    country: str | None = None
    status: str
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    results_count: int = 0
    risk_score_value: float | None = None
    risk_level: str | None = None
    sources_searched: list[str] | None = None


class SearchResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_name: str
    category: str
    title: str
    description: str | None = None
    url: str | None = None
    event_date: str | None = None
    subject_name: str | None = None
    location: str | None = None
    confidence: float
    risk_contribution: float


class SearchDetail(SearchOut):
    results: list[SearchResultOut] = []
    report_reference: str | None = None


class PaginatedSearches(BaseModel):
    items: list[SearchOut]
    total: int
    page: int
    page_size: int


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    display_name: str
    description: str | None = None
    enabled: bool


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    search_id: str | None = None
    action: str
    details: dict | None = None
    timestamp: datetime


class DashboardStats(BaseModel):
    total_searches: int
    running_searches: int
    completed_searches: int
    failed_searches: int
    high_risk_searches: int
    recent_searches: list[SearchOut]
    high_risk_recent: list[SearchOut]
