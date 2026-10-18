@echo off
REM PyGBSentry doctor: environment self-check. Paste the output into your issue.
setlocal enabledelayedexpansion
cd /d "%~dp0backend"
echo ===== PyGBSentry doctor report =====
echo [1] OS: %OS%

echo [2] Python:
python --version 2>nul || echo   python not found
python -c "import sys; print('   executable:', sys.executable)" 2>nul

echo [3] venv:
if exist venv\Scripts\python.exe (echo   venv exists) else (echo   venv MISSING - run install.bat)

echo [4] .env:
if exist .env (echo   .env exists) else (echo   .env MISSING - run install.bat)
for /f "tokens=2 delims==" %%a in ('findstr /b DATABASE_TYPE= .env 2^>nul') do echo   DATABASE_TYPE=%%a
for /f "tokens=2 delims==" %%a in ('findstr /b BACKEND_PUBLIC_PORT= .env 2^>nul') do echo   BACKEND_PUBLIC_PORT=%%a
for /f "tokens=2 delims==" %%a in ('findstr /b PLUGIN_MARKETPLACE_BASE_URL= .env 2^>nul') do echo   MARKETPLACE=%%a

echo [5] Frontend dist:
if exist ..\frontend\dist\index.html (echo   dist exists) else (echo   dist MISSING - git pull or re-download)

echo [6] Ports LISTENING (8000/8010/5062):
netstat -ano | findstr ":8000 :8010 :5062 " | findstr LISTENING
echo ===== end of report =====
echo.
echo Paste everything above into your Gitee issue if you need help.
pause
