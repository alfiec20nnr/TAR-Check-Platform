@echo off
REM Stops the Adverse Intelligence Platform started by start.bat or
REM start-hidden.vbs (finds the hidden server process and ends it).
title Stop Adverse Intelligence Platform
echo Stopping the Adverse Intelligence Platform...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*uvicorn app.main*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Done. You can close this window.
ping -n 4 127.0.0.1 >nul
