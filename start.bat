@echo off
REM ============================================================================
REM  Adverse Intelligence Platform - one-click start, no Docker required
REM
REM  First time: sets everything up automatically - takes a few minutes and
REM  needs an internet connection once. After that: starts in seconds.
REM  Close this window to stop the platform.
REM
REM  The only one-time install you need (all defaults are fine):
REM    - Python 3.11+   https://www.python.org/downloads/
REM      IMPORTANT: tick "Add Python to PATH" during installation.
REM
REM  The web interface ships pre-built, so Node.js is NOT needed - it is only
REM  required if you change the frontend source code yourself.
REM ============================================================================
setlocal EnableExtensions
title Adverse Intelligence Platform
cd /d "%~dp0"

REM ---- Guard: the whole project folder must be here, not just this file ------
if not exist "backend\requirements.txt" goto notextracted

REM ---- Already running? Open its browser tab instead of failing --------------
REM The health check only answers if the platform is up (curl ships with
REM Windows 10+; if curl is somehow missing this check is skipped harmlessly).
curl -s -o nul --max-time 2 http://127.0.0.1:8000/health 2>nul
if not errorlevel 1 goto alreadyrunning

REM ---- Create .env from example if missing ------------------------------------
if not exist ".env" (
    if exist ".env.example" (
        echo Creating .env from .env.example - edit it to add your API keys.
        copy /y ".env.example" ".env" >nul
    )
)

REM ---- Find a real Python - the Microsoft Store stub does not count ----------
set "PYTHON="
python -c "import sys" >nul 2>nul
if not errorlevel 1 set "PYTHON=python"
if defined PYTHON goto python_found
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PYTHON=py -3"
if defined PYTHON goto python_found
goto nopython
:python_found

REM ---- Require Python 3.11 or newer -------------------------------------------
%PYTHON% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto oldpython

REM ---- Web interface - a pre-built copy ships with the project ----------------
if exist "frontend\dist\index.html" goto frontend_ok
where npm >nul 2>nul
if errorlevel 1 goto nonode
echo [1/4] Building the web interface - one time only, please wait...
cd frontend
call npm install --no-fund --no-audit
if errorlevel 1 goto fail
call npm run build
if errorlevel 1 goto fail
cd ..
goto frontend_done
:frontend_ok
echo [1/4] Web interface ready.
:frontend_done

REM ---- Python environment -----------------------------------------------------
REM The environment lives OUTSIDE the project folder, in the user profile.
REM Keeping thousands of package files out of OneDrive/Dropbox-synced folders
REM stops cloud sync from slowing startup down or "freeing up" the files, and
REM means copying the project to another computer never drags a stale
REM environment along. (Not AppData: the Microsoft Store build of Python
REM silently redirects AppData writes into its own sandbox.) Override the
REM location with AIP_VENV_DIR if needed.
set "VENV=%USERPROFILE%\.aip\venv"
if defined AIP_VENV_DIR set "VENV=%AIP_VENV_DIR%"
set "VENVPY=%VENV%\Scripts\python.exe"
cd backend
set "VENV_REBUILT="

:venv_check
if not exist "%VENVPY%" goto venv_create
"%VENVPY%" -c "import sys" >nul 2>nul
if errorlevel 1 goto venv_rebuild
goto venv_ready

:venv_rebuild
if defined VENV_REBUILT goto fail
set "VENV_REBUILT=1"
echo The Python environment is damaged or incomplete.
echo Rebuilding it fresh - this takes a few minutes...
if exist "%VENV%" rmdir /s /q "%VENV%"

:venv_create
echo [2/4] Creating Python environment...
%PYTHON% -m venv "%VENV%"
if errorlevel 1 goto fail

:venv_ready
REM Skip the slow pip run entirely when requirements.txt has not changed
REM since the last successful install (the stamp is a copy taken on success).
fc /b requirements.txt "%VENV%\requirements.stamp" >nul 2>nul
if not errorlevel 1 goto deps_ready
echo [2/4] Installing dependencies - can take a few minutes on first run...
"%VENVPY%" -m pip install -q -r requirements.txt
if errorlevel 1 goto venv_rebuild
REM Verify the key packages actually import - catches interrupted or
REM half-finished installs that pip alone does not notice.
"%VENVPY%" -c "import aiosqlite, fastapi, uvicorn, alembic" >nul 2>nul
if errorlevel 1 goto venv_rebuild
copy /y requirements.txt "%VENV%\requirements.stamp" >nul
:deps_ready
echo [2/4] Python environment ready.

REM ---- Database + configuration ------------------------------------------------
REM Single-process mode: local SQLite database file, pipeline runs in-process.
REM All other settings such as API keys are read from the .env file at the
REM project root - the same file Docker uses.
set "DATABASE_URL=sqlite+aiosqlite:///./aip.sqlite3"
set "INLINE_WORKER=true"
set "AUTO_SHUTDOWN_AFTER_SECONDS=90"
set "OPEN_BROWSER_URL=http://localhost:8000"

echo [3/4] Preparing the database and starting the platform...
echo.
echo  ============================================================
echo   Adverse Intelligence Platform is starting.
echo   A browser tab will open automatically once it is ready at:
echo   http://localhost:8000
echo.
echo   The platform stops by itself shortly after you close its
echo   browser tab. Closing this window also stops it.
echo  ============================================================
echo.
REM One interpreter does everything - encryption key, database migrations,
REM connector seeding, then the web server (see backend/app/launch.py).
"%VENVPY%" -m app.launch
if errorlevel 1 goto serverfail
echo.
echo  The platform has stopped.
ping -n 3 127.0.0.1 >nul
exit /b 0

:alreadyrunning
echo.
echo  The platform is already running - opening it in your browser...
echo  (Nothing else to do; this window will close by itself.)
start "" http://localhost:8000
ping -n 4 127.0.0.1 >nul
exit /b 0

:serverfail
echo.
echo  The platform could not start, or stopped unexpectedly - see the
echo  messages above.
echo    - If another program is using port 8000, close it and try again.
echo    - If the Python environment looks damaged, delete this folder and
echo      run start.bat again to rebuild it:
echo        %VENV%
echo.
if not defined AIP_NO_PAUSE pause
exit /b 1

:notextracted
echo.
echo  The rest of the project files were not found next to this script.
echo  If you downloaded a ZIP, right-click it and choose "Extract All",
echo  then open the extracted folder and double-click start.bat there.
echo.
if not defined AIP_NO_PAUSE pause
exit /b 1

:nopython
echo.
echo  Python was not found on this computer.
echo  Please install it from:  https://www.python.org/downloads/
echo  IMPORTANT: tick "Add Python to PATH" during installation, then
echo  double-click this file again.
echo.
if not defined AIP_NO_PAUSE pause
exit /b 1

:oldpython
echo.
echo  Your Python is too old - the platform needs Python 3.11 or newer.
echo  Please install the latest version from:
echo      https://www.python.org/downloads/
echo  IMPORTANT: tick "Add Python to PATH" during installation, then
echo  double-click this file again.
echo.
if not defined AIP_NO_PAUSE pause
exit /b 1

:nonode
echo.
echo  The web interface is missing its pre-built files, and Node.js was
echo  not found to rebuild them. This usually means an incomplete download.
echo  Re-download the project, or install Node.js LTS from https://nodejs.org
echo  and double-click this file again.
echo.
if not defined AIP_NO_PAUSE pause
exit /b 1

:fail
echo.
echo  Something went wrong - see the messages above.
echo  If you are stuck, send a screenshot of this window to your
echo  technical contact.
if not defined AIP_NO_PAUSE pause
exit /b 1
