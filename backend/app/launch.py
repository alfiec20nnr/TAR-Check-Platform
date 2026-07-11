"""Single-process launcher for the no-Docker start scripts.

Everything a launch needs happens in ONE interpreter — encryption-key check,
database migrations, connector seeding, then the web server. The start
scripts previously ran each of those as a separate ``python -m …`` process,
and those four consecutive interpreter start-ups (each importing SQLAlchemy /
the app) dominated warm start time.

The Docker stack does not use this module: docker-compose runs alembic and
app.seed explicitly and starts uvicorn directly.

Run from backend/:  python -m app.launch
"""

import asyncio
import logging
import os


async def _seed_and_reset_engine() -> None:
    """Seed the connector registry, then drop the cached engine.

    Seeding runs on this temporary event loop; the server creates its own.
    Async connections cannot cross event loops, so the engine cached by
    app.database must be disposed and forgotten before uvicorn starts.
    """
    from app.database import get_engine, reset_engine
    from app.seed import seed_sources

    await seed_sources()
    await get_engine().dispose()
    reset_engine()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Encryption key first — everything after this point reads settings (and
    # therefore .env) and caches them, so the key must already be in place.
    from app.ensure_key import main as ensure_key

    ensure_key()

    from alembic.config import Config

    from alembic import command

    command.upgrade(Config("alembic.ini"), "head")

    asyncio.run(_seed_and_reset_engine())

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.environ.get("AIP_HOST", "127.0.0.1"),
        port=int(os.environ.get("AIP_PORT", "8000")),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
