@echo off
REM PyGBSentry update: git pull + refresh dependencies + sync database
setlocal
cd /d "%~dp0"
echo [1/3] git pull ...
git pull
if errorlevel 1 (
    echo [FAIL] git pull failed - commit or stash your local edits first.
    pause
    exit /b 1
)
cd backend
if exist venv call venv\Scripts\activate.bat
echo [2/3] Refreshing dependencies ...
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple -q
echo [3/3] Syncing database ...
python app\initial_data.py
echo.
echo [ OK ] Update done. Double-click start.bat (restart if running - or use stop.bat first).
pause
