#!/usr/bin/env bash
# =============================================================================
#  Adverse Intelligence Platform - one-command start (no Docker required)
#
#  First time: sets everything up automatically. Ctrl+C stops the platform.
#  Requirements: Python 3.11+. (Node.js is only needed if you change the
#  frontend source — a pre-built web interface ships with the project.)
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null; then
    echo "Python was not found. Install Python 3.11+ and re-run." >&2
    exit 1
fi

if [ ! -f .env ] && [ -f .env.example ]; then
    echo "Creating .env from .env.example - edit it to add your API keys."
    cp .env.example .env
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
# The Python environment lives OUTSIDE the project folder, in per-machine app
# data: cloud-sync tools (OneDrive/Dropbox/iCloud) then never slow startup by
# syncing or evicting thousands of package files, and copying the project to
# another computer never drags a stale environment along. Override with
# AIP_VENV_DIR if needed.
VENV="${AIP_VENV_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/adverse-intelligence-platform/venv}"
PY="$VENV/bin/python"
if [ -e "$VENV" ] && ! "$PY" -c "import sys" >/dev/null 2>&1; then
    echo "The Python environment is damaged or incomplete - rebuilding..."
    rm -rf "$VENV"
fi
if [ ! -x "$PY" ]; then
    echo "[2/4] Creating Python environment (first run only)..."
    python3 -m venv "$VENV"
fi
echo "[2/4] Installing/updating dependencies..."
"$PY" -m pip install -q -r requirements.txt
# Catch interrupted or half-finished installs that pip alone does not notice.
if ! "$PY" -c "import aiosqlite, fastapi, uvicorn, alembic" >/dev/null 2>&1; then
    echo "Environment verification failed - rebuilding fresh..."
    rm -rf "$VENV"
    python3 -m venv "$VENV"
    "$PY" -m pip install -q -r requirements.txt
fi

# Encryption key: generated on first run so personal data is encrypted at
# rest. An existing key in .env is never overwritten.
"$PY" -m app.ensure_key

# Single-process mode: SQLite database, pipeline runs in-process. All other
# settings (API keys etc.) come from the .env file at the project root.
export DATABASE_URL="sqlite+aiosqlite:///./aip.sqlite3"
export INLINE_WORKER=true
export AUTO_SHUTDOWN_AFTER_SECONDS=90
export OPEN_BROWSER_URL="http://localhost:8000"

echo "[3/4] Preparing the database..."
"$PY" -m alembic upgrade head
"$PY" -m app.seed

echo "[4/4] Starting the platform at http://localhost:8000 (Ctrl+C to stop)..."
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
