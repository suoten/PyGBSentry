@echo off
REM =============================================================
REM  PyGBSentry one-click installer (Windows, double-click to run)
REM  Quick mode: SQLite. No PostgreSQL / Redis / Node.js needed.
REM  After install: double-click start.bat, open http://localhost:PORT
REM =============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ==============================================
echo    PyGBSentry Installer - Windows SQLite quick mode
echo ==============================================
echo.

REM ---------- 1. Find Python 3.11-3.13 ----------
echo [1/6] Checking Python - need 3.11 to 3.13 ...
set "PY_BIN="
for %%P in (py python python3) do (
    if not defined PY_BIN (
        %%P -c "import sys; assert sys.version_info[0] == 3 and 11 <= sys.version_info[1] <= 13" >nul 2>&1 && set "PY_BIN=%%P"
    )
)
if not defined PY_BIN (
    py -3.12 -c "import sys" >nul 2>&1 && set "PY_BIN=py -3.12"
)
if not defined PY_BIN (
    py -3.11 -c "import sys" >nul 2>&1 && set "PY_BIN=py -3.11"
)

if not defined PY_BIN (
    echo.
    echo [FAIL] No suitable Python found.
    echo.
    echo This project requires Python 3.11 - 3.13.
    echo Python 3.8 / 3.9 / 3.10 will NOT work - syntax errors.
    echo.
    echo How to install:
    echo   Official:  https://www.python.org/downloads/release/python-3128/
    echo              CHECK "Add python.exe to PATH" during setup
    echo   CN mirror: https://mirrors.huaweicloud.com/python/
    echo   Zero-install option: see README section "Portable build"
    echo.
    echo Then run install.bat again.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('%PY_BIN% -c "import sys; print(str(sys.version_info[0])+chr(46)+str(sys.version_info[1]))"') do set PY_VER=%%v
echo [ OK ] Found Python %PY_VER%

REM ---------- 2. venv ----------
echo [2/6] Creating virtual environment ...
cd backend
if exist venv goto :venv_ok
%PY_BIN% -m venv venv
if errorlevel 1 (
    echo [FAIL] Failed to create venv. Please report the error above.
    pause
    exit /b 1
)
:venv_ok
call venv\Scripts\activate.bat
echo [ OK ] venv ready

REM ---------- 3. dependencies ----------
echo [3/6] Installing backend dependencies - 1 to 3 minutes ...
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo Tsinghua mirror failed - retrying with official PyPI ...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [FAIL] Dependency install failed. Check network and retry.
        pause
        exit /b 1
    )
)
echo [ OK ] Dependencies installed

REM ---------- 4. .env ----------
echo [4/6] Generating .env ...
if exist .env goto :env_ok
copy .env.example .env >nul

set "ADMIN_PWD_SET="
set /p "ADMIN_PWD_SET=Set admin password (press Enter to auto-generate): "

python -c "import io,re,secrets,os; p='.env'; s=io.open(p,encoding='utf-8').read(); s=re.sub('(?m)^DATABASE_TYPE=postgresql','DATABASE_TYPE=sqlite',s); s=re.sub('(?m)^SECRET_KEY=.*','SECRET_KEY=\"'+secrets.token_hex(32)+'\"',s); s=re.sub('(?m)^FIELD_ENCRYPTION_KEY=.*','FIELD_ENCRYPTION_KEY=\"'+secrets.token_hex(32)+'\"',s); pwd=os.environ.get('ADMIN_PWD_SET','').strip() or secrets.token_urlsafe(9); s=re.sub('(?m)^ADMIN_INITIAL_PASSWORD=.*','ADMIN_INITIAL_PASSWORD=\"'+pwd+'\"',s); io.open(p,'w',encoding='utf-8').write(s); io.open('../ADMIN_PASSWORD.txt','w',encoding='utf-8').write('PyGBSentry admin account\n\nuser:     admin\npassword: '+pwd+'\n\nKeep this file safe. Change the password after first login.\n'); print('  ADMIN_PASSWORD = '+pwd)"
if exist "..\ADMIN_PASSWORD.txt" (
    echo [ OK ] .env generated - SQLite quick mode
    echo [ OK ] Credentials saved to ADMIN_PASSWORD.txt
) else (
    echo [ OK ] .env generated
)
goto :port_check

:env_ok
echo [SKIP] .env already exists - keeping your config

:port_check
REM ---------- 4.5 port conflict: auto-pick a free port ----------
set "PORT=8000"
netstat -ano | findstr ":8000 " | findstr LISTENING >nul 2>&1
if errorlevel 1 goto :port_ok
for %%Q in (8010 8080 8888 9000) do (
    netstat -ano | findstr ":%%Q " | findstr LISTENING >nul 2>&1
    if errorlevel 1 (
        set "PORT=%%Q"
        goto :port_found
    )
)
echo [WARN] Ports 8000/8010/8080/8888/9000 all busy - edit BACKEND_PUBLIC_PORT in backend\.env
goto :port_ok
:port_found
python -c "import io,re; p='.env'; s=io.open(p,encoding='utf-8').read(); s=re.sub('(?m)^BACKEND_PUBLIC_PORT=.*','BACKEND_PUBLIC_PORT=%PORT%',s); io.open(p,'w',encoding='utf-8').write(s)"
echo [ OK ] Port 8000 busy - switched to %PORT% (saved in .env)

:port_ok
echo [ OK ] Using port %PORT%

REM ---------- 5. database ----------
echo [5/6] Initializing database - tables + admin user ...
python app\initial_data.py
if errorlevel 1 (
    echo [FAIL] Database init failed. Please report the full error above.
    pause
    exit /b 1
)
echo [ OK ] Database ready

REM ---------- 6. frontend ----------
if exist ..\frontend\dist\index.html (
    echo [6/6] Frontend dist found - UI will be served by the backend
) else (
    echo [6/6] [WARN] frontend\dist missing - run: git pull  then re-run install.bat
)

REM ---------- done ----------
echo.
echo ==============================================
echo    Install DONE
echo ==============================================
echo.
echo   Start:      double-click start.bat
echo   Platform:   http://localhost:%PORT%   (web UI opens automatically)
echo   Admin user: admin
echo   Admin pass: see ADMIN_PASSWORD.txt  ^(or backend\.env^)
echo.
echo   Also: stop.bat  update.bat  doctor.bat
echo   Docs: docs\INSTALL.md    Issues: gitee.com/suoten/PyGBSentry/issues
echo.
pause
