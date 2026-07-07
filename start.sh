#!/usr/bin/env bash
# =============================================================================
#  Adverse Intelligence Platform - one-command start (no Docker required)
#
#  First time: sets everything up automatically. Ctrl+C stops the platform.
#  Requirements: Python 3.11+; Node.js LTS (first run only, to build the UI).
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null; then
    echo "Python was not found. Install Python 3.11+ and re-run." >&2
    exit 1
fi

if [ ! -f frontend/dist/index.html ]; then
    if ! command -v npm >/dev/null; then
        echo "The web interface is not built yet and Node.js was not found." >&2
        echo "Install Node.js LTS (https://nodejs.org) and re-run - it is" >&2
        echo "only needed this first time." >&2
        exit 1
    fi
    echo "[1/4] Building the web interface (first run only)..."
    (cd frontend && npm install --no-fund --no-audit && npm run build)
else
    echo "[1/4] Web interface already built."
fi

cd backend
if [ ! -x .venv/bin/python ]; then
    echo "[2/4] Creating Python environment (first run only)..."
    python3 -m venv .venv
fi
echo "[2/4] Installing/updating dependencies..."
.venv/bin/python -m pip install -q -r requirements.txt

# Single-process mode: SQLite database, pipeline runs in-process. All other
# settings (API keys etc.) come from the .env file at the project root.
export DATABASE_URL="sqlite+aiosqlite:///./aip.sqlite3"
export INLINE_WORKER=true

echo "[3/4] Preparing the database..."
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.seed

echo "[4/4] Starting the platform at http://localhost:8000 (Ctrl+C to stop)..."
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
