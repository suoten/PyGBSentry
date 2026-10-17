@echo off
REM PyGBSentry launcher (Windows): activate venv and start backend
cd /d "%~dp0backend"

if not exist venv (
    echo [FAIL] venv not found. Double-click install.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat

set "PORT=8000"
for /f "tokens=2 delims==" %%a in ('findstr /b BACKEND_PUBLIC_PORT= .env 2^>nul') do set PORT=%%a

echo [PyGBSentry] Starting backend - http://localhost:%PORT%
echo [PyGBSentry] API docs      - http://localhost:%PORT%/docs
echo [PyGBSentry] Press Ctrl+C in this window to stop
python -m app.main
pause
