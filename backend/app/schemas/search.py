"""Pydantic schemas for the public REST API."""

import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_LICENCE_NUMBER_RE = re.compile(r"^[A-Z0-9]{8,18}$")


class SearchCreate(BaseModel):
    """Search input — deliberately minimal (data minimisation)."""

    full_name: str = Field(min_length=2, max_length=200, description="Full name (required)")
    date_of_birth: date | None = Field(default=None, description="Date of birth (optional)")
    country: str | None = Field(default=None, max_length=64, description="Country (optional)")
    driving_licence_number: str | None = Field(
        default=None,
        max_length=24,
        description=(
            "Driving licence number (optional) — enables the DVLA licence check. "
            "Requires licence_check_consent."
        ),
    )
    licence_check_consent: bool = Field(
        default=False,
        description=(
            "Attestation that the driver has consented to a DVLA licence data "
            "check. Mandatory when a licence number is supplied."
        ),
    )

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

    @field_validator("driving_licence_number")
    @classmethod
    def normalise_licence_number(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = re.sub(r"[\s-]", "", v).upper()
        if not v:
            return None
        if not _LICENCE_NUMBER_RE.fullmatch(v):
            raise ValueError(
                "driving_licence_number must be 8-18 letters/digits"
            )
        return v

    @model_validator(mode="after")
    def licence_requires_consent(self) -> "SearchCreate":
        if self.driving_licence_number and not self.licence_check_consent:
            raise ValueError(
                "licence_check_consent is required when a driving licence "
                "number is supplied (the driver must have consented to the check)"
            )
        return self


class SearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    date_of_birth: str | None = None
    country: str | None = None
    created_by: str | None = None  # username; None on pre-multi-user rows
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
    # Whether the connector has the credentials it needs to run live. In mock
    # mode every source reports True (fixtures need no keys).
    configured: bool = True


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    search_id: str | None = None
    actor: str | None = None  # username; None for system actions
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
