"""FastAPI application entry point.

Runs locally / inside a trusted network — no authentication by design (MVP).
Application-level protections that do apply: input validation (Pydantic),
rate limiting, CORS, security headers, parameterised queries (SQLAlchemy),
and encryption-at-rest for personal data.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

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


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


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
