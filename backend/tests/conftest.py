"""Test configuration.

The test environment is set *before* any app module is imported: SQLite
database, mock connectors, inline worker, no AI key (template fallback).
"""

import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="aip-test-")
os.environ.update(
    {
        "DATABASE_URL": f"sqlite+aiosqlite:///{_TMP_DIR}/test.sqlite3",
        "MOCK_CONNECTORS": "true",
        "INLINE_WORKER": "true",
        "ANTHROPIC_API_KEY": "",
        "ENCRYPTION_KEY": "",
        "API_RATE_LIMIT": "1000/minute",
        "CORS_ORIGINS": "http://testserver",
    }
)

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app import database  # noqa: E402
from app import models  # noqa: F401, E402  (imported to register tables)
from app.config import get_settings  # noqa: E402
from app.database import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _settings_cache():
    get_settings.cache_clear()
    yield


@pytest.fixture(autouse=True)
async def _prepare_db():
    """Fresh schema for every test."""
    engine = database.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def settings():
    return get_settings()
