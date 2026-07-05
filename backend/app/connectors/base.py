"""Connector framework.

Every data source implements :class:`BaseConnector`. The base class provides:

- independent execution with a hard timeout
- retries with exponential backoff for transient HTTP failures
- per-connector outbound rate limiting (simple async token interval)
- failure logging and execution timing
- a common normalised output shape (:class:`Finding`)

New sources are added by subclassing ``BaseConnector`` and registering the
class in :mod:`app.connectors.registry` — no core code changes required.
"""

import asyncio
import enum
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from rapidfuzz import fuzz

from app.config import Settings

logger = logging.getLogger(__name__)


def screening_score(subject_name: str, candidate_name: str) -> float:
    """Name-similarity score used by connectors to screen candidate records.

    token_set_ratio tolerates extra name parts (middle names, patronymics) so a
    true hit cannot hide behind them — but only when BOTH names carry at least
    two tokens. A single-token name (e.g. the sanctions codename alias "Green")
    would otherwise trivially match any subject sharing that one word.
    """
    normalise = lambda s: " ".join(re.sub(r"[^\w\s'-]", " ", s.lower()).split())  # noqa: E731
    a, b = normalise(subject_name), normalise(candidate_name)
    if not a or not b:
        return 0.0
    if len(a.split()) >= 2 and len(b.split()) >= 2:
        return float(fuzz.token_set_ratio(a, b))
    return float(fuzz.token_sort_ratio(a, b))


# Normalised finding categories, referenced by the risk-scoring config.
class Category:
    SANCTIONS = "sanctions"
    DISQUALIFICATION = "disqualification"
    INSOLVENCY = "insolvency"
    REGULATORY = "regulatory"
    ADVERSE_MEDIA = "adverse_media"
    DIRECTORSHIP = "directorship"
    WEB = "web"


@dataclass
class SearchSubject:
    """The individual being searched for."""

    full_name: str
    date_of_birth: str | None = None  # ISO date string
    country: str | None = None


@dataclass
class Finding:
    """A single normalised record returned by any connector."""

    source: str
    category: str
    title: str
    description: str | None = None
    url: str | None = None
    date: str | None = None  # ISO date string where known
    subject_name: str | None = None  # name as it appears in the source record
    location: str | None = None
    date_of_birth: str | None = None  # DOB as surfaced by the source (may be partial)
    raw: dict[str, Any] = field(default_factory=dict)


class ConnectorStatus(enum.StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"  # not configured (e.g. missing API key)


@dataclass
class ConnectorResult:
    connector: str
    status: ConnectorStatus
    findings: list[Finding] = field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0


class _RateLimiter:
    """Minimal async rate limiter: at most `rate` calls per second."""

    def __init__(self, rate_per_second: float):
        self._interval = 1.0 / rate_per_second if rate_per_second > 0 else 0.0
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def acquire(self) -> None:
        if self._interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            wait = self._last + self._interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


class BaseConnector:
    """Base class for all data-source connectors."""

    #: unique machine name; must match the Sources registry row
    name: str = "base"
    display_name: str = "Base connector"
    description: str = ""

    RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}

    def __init__(self, settings: Settings):
        self.settings = settings
        self._limiter = _RateLimiter(settings.connector_rate_limit_per_second)

    # -- interface -------------------------------------------------------------

    def is_configured(self) -> bool:
        """Whether the connector has the credentials/config it needs."""
        return True

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        """Query the source and return normalised findings. Subclasses implement."""
        raise NotImplementedError

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        """Fixture data used when MOCK_CONNECTORS is enabled."""
        return []

    # -- execution -------------------------------------------------------------

    async def run(self, subject: SearchSubject) -> ConnectorResult:
        """Execute the connector with timing, retries and error capture."""
        start = time.monotonic()

        def _elapsed() -> int:
            return int((time.monotonic() - start) * 1000)

        if self.settings.mock_connectors:
            findings = self.mock_findings(subject)
            return ConnectorResult(
                connector=self.name,
                status=ConnectorStatus.SUCCESS,
                findings=findings,
                duration_ms=_elapsed(),
            )

        if not self.is_configured():
            logger.info("Connector %s skipped — not configured", self.name)
            return ConnectorResult(
                connector=self.name,
                status=ConnectorStatus.SKIPPED,
                error="not configured",
                duration_ms=_elapsed(),
            )

        timeout = httpx.Timeout(self.settings.connector_timeout_seconds)
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            for attempt in range(self.settings.connector_max_retries + 1):
                await self._limiter.acquire()
                try:
                    findings = await self.fetch(subject, client)
                    return ConnectorResult(
                        connector=self.name,
                        status=ConnectorStatus.SUCCESS,
                        findings=findings,
                        duration_ms=_elapsed(),
                    )
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    if exc.response.status_code not in self.RETRYABLE_STATUS:
                        break
                except (TimeoutError, httpx.TransportError) as exc:
                    last_error = exc
                if attempt < self.settings.connector_max_retries:
                    await asyncio.sleep(0.5 * 2**attempt)

        logger.error("Connector %s failed: %s", self.name, last_error)
        return ConnectorResult(
            connector=self.name,
            status=ConnectorStatus.FAILED,
            error=str(last_error),
            duration_ms=_elapsed(),
        )
