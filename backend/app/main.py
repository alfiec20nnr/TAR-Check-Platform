"""FastAPI application entry point.

Runs locally / inside a trusted network — no authentication by design (MVP).
Application-level protections that do apply: input validation (Pydantic),
rate limiting, CORS, security headers, parameterised queries (SQLAlchemy),
and encryption-at-rest for personal data.
"""

import asyncio
import logging
import os
import signal
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.routes import dashboard, reports, searches
from app.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

settings = get_settings()

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.api_rate_limit])

app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Adverse-media and public-record due diligence for individuals. "
        "Submit a search, poll its status, and retrieve the generated report."
    ),
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# --- Auto-shutdown (single-process / no-Docker mode) ---------------------------
# The UI heartbeats while a tab is open and beacons when one closes. Once no
# tab remains and requests stop, the server exits by itself — no stop script
# needed. Disabled unless AUTO_SHUTDOWN_AFTER_SECONDS is set (Docker never
# sets it). A running search always defers shutdown.


class AutoShutdownState:
    TAB_CLOSE_GRACE = 15.0  # ride out refreshes/navigation
    IDLE_WITH_NO_TABS = 20.0  # and require requests to have actually stopped

    def __init__(self, idle_timeout: float):
        self.idle_timeout = idle_timeout  # hard fallback (browser crash/kill)
        self.last_seen = time.monotonic()
        self.open_tabs = 0
        self.ever_opened = False
        self._zero_since: float | None = None

    def touch(self) -> None:
        self.last_seen = time.monotonic()

    def tab_opened(self) -> None:
        self.open_tabs += 1
        self.ever_opened = True
        self.touch()

    def tab_closed(self) -> None:
        self.open_tabs = max(0, self.open_tabs - 1)
        self.touch()

    def due(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        if now - self.last_seen >= self.idle_timeout:
            return True
        if not self.ever_opened or self.open_tabs > 0:
            self._zero_since = None
            return False
        if self._zero_since is None:
            self._zero_since = now
        return (
            now - self._zero_since >= self.TAB_CLOSE_GRACE
            and now - self.last_seen >= self.IDLE_WITH_NO_TABS
        )


_shutdown_state: AutoShutdownState | None = (
    AutoShutdownState(float(settings.auto_shutdown_after_seconds))
    if settings.auto_shutdown_after_seconds > 0
    else None
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if _shutdown_state is not None:
        _shutdown_state.touch()
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.post("/api/v1/session/open", status_code=204, tags=["session"])
async def session_open() -> None:
    """Browser tab opened (no-op unless auto-shutdown mode is active)."""
    if _shutdown_state is not None:
        _shutdown_state.tab_opened()


@app.post("/api/v1/session/close", status_code=204, tags=["session"])
async def session_close() -> None:
    """Browser tab closed (sent via sendBeacon on pagehide)."""
    if _shutdown_state is not None:
        _shutdown_state.tab_closed()


async def _has_active_searches() -> bool:
    from sqlalchemy import func, select

    from app.database import get_session_factory
    from app.models import Search, SearchStatus

    async with get_session_factory()() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(Search)
                .where(
                    Search.status.in_(
                        (SearchStatus.PENDING.value, SearchStatus.RUNNING.value)
                    )
                )
            )
        ).scalar_one()
    return bool(count)


@app.on_event("startup")
async def _start_auto_shutdown_watchdog() -> None:
    if _shutdown_state is None:
        return
    logger = logging.getLogger(__name__)
    logger.info(
        "Auto-shutdown armed: stopping when the browser closes "
        "(fallback after %ss of no activity)",
        settings.auto_shutdown_after_seconds,
    )

    async def watchdog() -> None:
        while True:
            await asyncio.sleep(3)
            if not _shutdown_state.due():
                continue
            if await _has_active_searches():
                continue  # never cut a search short
            logger.info("Browser closed and no activity — shutting down")
            signal.raise_signal(signal.SIGINT)  # graceful uvicorn stop
            await asyncio.sleep(10)
            os._exit(0)  # hard fallback if graceful stop stalls

    asyncio.get_running_loop().create_task(watchdog())


async def _single_process_housekeeping() -> None:
    """Recovery + retention work the dedicated worker does in the Docker stack.

    Single-process mode has no worker, so at startup the API process itself:

    - Fails searches left pending/running by a previous shutdown or crash.
      Their in-process pipeline task died with the server, so they could never
      finish — and a permanently "running" search would also block
      auto-shutdown forever.
    - Applies the data-retention policy (children deleted explicitly because
      SQLite does not enforce ON DELETE CASCADE by default; audit entries are
      always kept).
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.api.routes.searches import _delete_search_rows
    from app.database import get_session_factory
    from app.models import Search, SearchStatus
    from app.services import audit

    logger = logging.getLogger(__name__)
    async with get_session_factory()() as session:
        stale = (
            (
                await session.execute(
                    select(Search).where(
                        Search.status.in_(
                            (SearchStatus.PENDING.value, SearchStatus.RUNNING.value)
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        for search in stale:
            search.status = SearchStatus.FAILED.value
            search.error = (
                "Interrupted — the platform was closed before this search "
                "finished. Please run the search again."
            )
            search.completed_at = datetime.now(UTC)
            await audit.record(
                session,
                "search_failed",
                search_id=search.id,
                details={"error": "interrupted by shutdown"},
            )
        if stale:
            logger.warning("Marked %d interrupted search(es) as failed", len(stale))

        cutoff = datetime.now(UTC) - timedelta(days=settings.data_retention_days)
        expired = list(
            (
                await session.execute(
                    select(Search.id).where(
                        Search.created_at < cutoff,
                        Search.status.in_(
                            (SearchStatus.COMPLETED.value, SearchStatus.FAILED.value)
                        ),
                    )
                )
            ).scalars()
        )
        if expired:
            await _delete_search_rows(session, expired)
            await audit.record(
                session, "retention_applied", details={"deleted": len(expired)}
            )
            logger.info("Retention policy removed %d search(es)", len(expired))
        await session.commit()


@app.on_event("startup")
async def _run_single_process_housekeeping() -> None:
    if settings.inline_worker:
        await _single_process_housekeeping()


@app.on_event("startup")
async def _open_browser_when_ready() -> None:
    """Open the UI once the server is actually reachable (start scripts set
    OPEN_BROWSER_URL). Polling first avoids the browser racing ahead of the
    server and showing "connection refused" on a cold start."""
    url = settings.open_browser_url
    if not url:
        return

    async def _poll_then_open() -> None:
        import webbrowser

        import httpx

        health_url = url.rstrip("/") + "/health"
        async with httpx.AsyncClient(timeout=1.0) as client:
            for _ in range(120):
                try:
                    await client.get(health_url)
                    break
                except httpx.HTTPError:
                    await asyncio.sleep(0.5)
            else:
                return  # never became reachable — give up quietly
        logging.getLogger(__name__).info("Opening browser at %s", url)
        webbrowser.open(url)

    asyncio.get_running_loop().create_task(_poll_then_open())


app.include_router(searches.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health() -> dict:
    # mock_connectors is surfaced so the UI can show a prominent demo-mode
    # banner — simulated fixture data must never be mistaken for real records.
    return {
        "status": "ok",
        "version": __version__,
        "mock_connectors": settings.mock_connectors,
    }


# --- Single-process mode (no Docker/nginx) -------------------------------------
# When a built frontend exists (frontend/dist), serve it directly so the whole
# application runs as one process on one URL. In the Docker stack nginx serves
# the SPA instead and this mount simply never activates (no dist in the image).
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():  # pragma: no branch

    class _SpaStaticFiles(StaticFiles):
        """Static files with SPA fallback: unknown paths get index.html so
        client-side routes like /searches/<id> work on refresh."""

        async def get_response(self, path: str, scope):  # type: ignore[override]
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code == 404:
                    return await super().get_response("index.html", scope)
                raise

    app.mount("/", _SpaStaticFiles(directory=_FRONTEND_DIST, html=True), name="spa")
    logger = logging.getLogger(__name__)
    logger.info("Serving frontend from %s (single-process mode)", _FRONTEND_DIST)
