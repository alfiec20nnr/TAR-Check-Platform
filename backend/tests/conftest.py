"""Test configuration.

The test environment is set *before* any app module is imported: SQLite
database, mock connectors, inline worker, no AI key (template fallback).
"""

import os
import tempfile

TEST_PASSWORD = "test-password"

_TMP_DIR = tempfile.mkdtemp(prefix="aip-test-")
os.environ.update(
    {
        "DATABASE_URL": f"sqlite+aiosqlite:///{_TMP_DIR}/test.sqlite3",
        "MOCK_CONNECTORS": "true",
        "INLINE_WORKER": "true",
        "ANTHROPIC_API_KEY": "",
        "ENCRYPTION_KEY": "",
        "API_RATE_LIMIT": "1000/minute",
        "AUTH_LOGIN_RATE_LIMIT": "1000/minute",
        "CORS_ORIGINS": "http://testserver",
        "AUTH_USERNAME": "admin",
        "AUTH_SECRET": "test-auth-secret",
    }
)

from app.auth import hash_password  # noqa: E402

# Low iteration count keeps the per-test login fast; the verify path reads
# the count from the stored hash, so production strength is unaffected.
os.environ["AUTH_PASSWORD_HASH"] = hash_password(TEST_PASSWORD, iterations=1000)

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
def _activated(monkeypatch):
    """Run every test as an activated machine; licensing tests override this."""
    monkeypatch.setattr("app.licensing.is_activated", lambda: True)


@pytest.fixture(autouse=True)
async def _prepare_db():
    """Fresh schema for every test, with the default user migrated from the
    legacy env credentials — every test therefore also exercises the
    .env → users-table upgrade path."""
    from app.seed import seed_default_user

    engine = database.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_default_user()
    yield


@pytest.fixture
async def client():
    """Logged-in client — the session cookie persists on the AsyncClient."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": TEST_PASSWORD},
        )
        assert resp.status_code == 204, "test login failed"
        yield ac


@pytest.fixture
async def anon_client():
    """Client without a session cookie, for testing the auth boundary."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def settings():
    return get_settings()
