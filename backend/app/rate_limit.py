"""Shared SlowAPI rate limiter.

Lives outside app.main so route modules can apply per-endpoint limits (e.g.
the tighter login limit) without importing the application module. Keyed by
client IP; behind the hosted reverse proxy uvicorn runs with --proxy-headers
so this sees the real client address rather than the proxy's.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

limiter = Limiter(
    key_func=get_remote_address, default_limits=[get_settings().api_rate_limit]
)
