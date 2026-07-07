@echo off
REM ============================================================================
REM  Adverse Intelligence Platform - one-click start, no Docker required
REM
REM  First time: sets everything up automatically - takes a few minutes.
REM  After that: starts in seconds. Close this window to stop the platform.
REM
REM  One-time installs, all defaults are fine:
REM    - Python 3.11+   https://www.python.org/downloads/
REM    - Node.js LTS    https://nodejs.org   - first run only
REM ============================================================================
setlocal EnableExtensions
title Adverse Intelligence Platform
cd /d "%~dp0"

REM ---- Find a real Python - the Microsoft Store stub does not count ----------
set "PYTHON="
python -c "import sys" >nul 2>nul
if not errorlevel 1 set "PYTHON=python"
if defined PYTHON goto python_ok
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PYTHON=py -3"
if defined PYTHON goto python_ok
goto nopython
:python_ok

REM ---- Build the web interface once - needs Node.js only the first time -----
if exist "frontend\dist\index.html" goto frontend_ok
where npm >nul 2>nul
if errorlevel 1 goto nonode
echo [1/4] Building the web interface - first run only, please wait...
cd frontend
call npm install --no-fund --no-audit
if errorlevel 1 goto fail
call npm run build
if errorlevel 1 goto fail
cd ..
goto frontend_done
:frontend_ok
echo [1/4] Web interface already built.
:frontend_done

REM ---- Python environment -----------------------------------------------------
cd backend
if exist ".venv\Scripts\python.exe" goto venv_ok
echo [2/4] Creating Python environment - first run only...
%PYTHON% -m venv .venv
if errorlevel 1 goto fail
:venv_ok
echo [2/4] Installing dependencies - can take a few minutes on first run...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 goto fail

REM ---- Database + configuration ------------------------------------------------
REM Single-process mode: local SQLite database file, pipeline runs in-process.
REM All other settings such as API keys are read from the .env file at the
REM project root - the same file Docker uses.
set "DATABASE_URL=sqlite+aiosqlite:///./aip.sqlite3"
set "INLINE_WORKER=true"

echo [3/4] Preparing the database...
".venv\Scripts\python.exe" -m alembic upgrade head
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m app.seed
if errorlevel 1 goto fail

echo [4/4] Starting the platform...
echo.
echo  ============================================================
echo   Adverse Intelligence Platform is running.
echo   Open your browser at:  http://localhost:8000
echo   A browser tab will open automatically.
echo.
echo   Keep this window open. Close it to stop the platform.
echo  ============================================================
echo.
start "" http://localhost:8000
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
echo.
echo  The platform has stopped.
pause
exit /b 0

:nopython
echo.
echo  Python was not found on this computer.
echo  Please install it from:  https://www.python.org/downloads/
echo  IMPORTANT: tick "Add Python to PATH" during installation, then
echo  double-click this file again.
echo.
pause
exit /b 1

:nonode
echo.
echo  The web interface has not been built yet, and Node.js was not found.
echo  Please install Node.js LTS from:  https://nodejs.org
echo  All defaults are fine. Node.js is only needed this first time.
echo  Then double-click this file again.
echo.
pause
exit /b 1

:fail
echo.
echo  Something went wrong - see the messages above.
echo  If you are stuck, send a screenshot of this window to your
echo  technical contact.
pause
exit /b 1
