@echo off
REM PyGBSentry launcher: opens the platform in your browser automatically
setlocal enabledelayedexpansion
cd /d "%~dp0backend"

if not exist venv (
    echo [FAIL] venv not found. Double-click install.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat

set "PORT=8000"
for /f "tokens=2 delims==" %%a in ('findstr /b BACKEND_PUBLIC_PORT= .env 2^>nul') do set PORT=%%a

netstat -ano | findstr ":%PORT% " | findstr LISTENING >nul 2>&1
if not errorlevel 1 (
    echo [INFO] PyGBSentry already running on port %PORT% - opening browser...
    start "" "http://localhost:%PORT%"
    timeout /t 2 >nul
    exit /b 0
)

start "" /min cmd /c "timeout /t 8 /nobreak >nul && start "" http://localhost:%PORT%"

title PyGBSentry - http://localhost:%PORT%
echo [PyGBSentry] Starting backend - http://localhost:%PORT%
echo [PyGBSentry] Keep this window OPEN - closing it stops the service.
echo [PyGBSentry] To stop: double-click stop.bat
python -m app.main
pause
