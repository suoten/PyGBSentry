@echo off
REM PyGBSentry stop: kills backend and SIP listener
setlocal
cd /d "%~dp0backend"
set "PORT=8000"
for /f "tokens=2 delims==" %%a in ('findstr /b BACKEND_PUBLIC_PORT= .env 2^>nul') do set PORT=%%a
set "SIP_PORT=5062"
for /f "tokens=2 delims==" %%a in ('findstr /b SIP_PORT= .env 2^>nul') do set SIP_PORT=%%a

set "KILLED=0"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do (
    taskkill /PID %%p /F >nul 2>&1 && set "KILLED=1"
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%SIP_PORT% " ^| findstr LISTENING') do (
    taskkill /PID %%p /F >nul 2>&1 && set "KILLED=1"
)
if "%KILLED%"=="1" (echo [ OK ] PyGBSentry stopped.) else (echo [INFO] PyGBSentry was not running.)
timeout /t 2 >nul
