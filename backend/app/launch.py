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


def _preflight_native_deps() -> None:
    """Fail fast with plain-English guidance if a native wheel can't load.

    pip installs the pre-built binary wheels (greenlet, cryptography, ...)
    without complaint, but they link against the Microsoft Visual C++
    runtime. On a machine that lacks it - notably Python installed via the
    Install Manager 'pythoncore' build, which does not ship that runtime - the
    DLLs only fail at import time, deep inside SQLAlchemy, with a cryptic
    "DLL load failed" traceback. Importing greenlet up front reproduces the
    same failure and lets us turn it into an actionable message.
    """
    try:
        import greenlet  # noqa: F401  (this import loads the _greenlet C extension)
    except ImportError as exc:
        if "DLL load failed" not in str(exc):
            raise
        print(
            "\n"
            " ============================================================\n"
            "  The platform is installed but a required Windows system\n"
            "  component is missing, so it cannot start.\n"
            "\n"
            "  Fix: install the Microsoft Visual C++ Redistributable (x64):\n"
            "    https://aka.ms/vs/17/release/vc_redist.x64.exe\n"
            "\n"
            "  Download it, run it, restart the computer, then double-click\n"
            "  start.bat again.\n"
            "\n"
            "  (Technical detail: a pre-built Python package could not load\n"
            "   because the Visual C++ runtime is missing - DLL load failed\n"
            "   while importing _greenlet.)\n"
            " ============================================================\n",
            flush=True,
        )
        raise SystemExit(1)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    _preflight_native_deps()

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
