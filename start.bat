@echo off
REM ============================================================================
REM  Adverse Intelligence Platform - one-click start (no Docker required)
REM
REM  First time: this sets everything up automatically (takes a few minutes).
REM  After that: it starts in seconds. Close this window to stop the platform.
REM
REM  Requirements (one-time installs, all defaults are fine):
REM    - Python 3.11+   https://www.python.org/downloads/  (tick "Add to PATH")
REM    - Node.js LTS    https://nodejs.org                  (first run only)
REM ============================================================================
setlocal
title Adverse Intelligence Platform
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo  Python was not found.
    echo  Please install it from https://www.python.org/downloads/
    echo  IMPORTANT: tick "Add Python to PATH" during installation, then
    echo  double-click this file again.
    echo.
    pause
    exit /b 1
)

REM --- Build the web interface once (needs Node.js only the first time) ------
if not exist "frontend\dist\index.html" (
    where npm >nul 2>nul
    if errorlevel 1 (
        echo.
        echo  The web interface has not been built yet, and Node.js was not
        echo  found. Please install Node.js LTS from https://nodejs.org
        echo  ^(all defaults are fine^), then double-click this file again.
        echo  Node.js is only needed this first time.
        echo.
        pause
        exit /b 1
    )
    echo [1/4] Building the web interface (first run only)...
    pushd frontend
    call npm install --no-fund --no-audit || goto :fail
    call npm run build || goto :fail
    popd
) else (
    echo [1/4] Web interface already built.
)

REM --- Python environment -----------------------------------------------------
cd backend
if not exist ".venv\Scripts\python.exe" (
    echo [2/4] Creating Python environment (first run only)...
    python -m venv .venv || goto :fail
)
echo [2/4] Installing/updating dependencies...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto :fail

REM --- Database + configuration ----------------------------------------------
REM Single-process mode: local SQLite database file, pipeline runs in-process.
REM All other settings (API keys etc.) are read from the .env file at the
REM project root - the same file Docker uses.
set "DATABASE_URL=sqlite+aiosqlite:///./aip.sqlite3"
set "INLINE_WORKER=true"

echo [3/4] Preparing the database...
".venv\Scripts\python.exe" -m alembic upgrade head || goto :fail
".venv\Scripts\python.exe" -m app.seed || goto :fail

echo [4/4] Starting the platform...
echo.
echo  ============================================================
echo   Adverse Intelligence Platform is running.
echo   Open your browser at:  http://localhost:8000
echo   (a browser tab will open automatically)
echo.
echo   Keep this window open. Close it to stop the platform.
echo  ============================================================
echo.
start "" http://localhost:8000
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
exit /b 0

:fail
echo.
echo  Something went wrong - see the messages above.
echo  If you are stuck, send the text above to your technical contact.
pause
exit /b 1
