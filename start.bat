@echo off
REM PyGBSentry 启动脚本（Windows）：激活虚拟环境并启动后端
chcp 65001 >nul
cd /d "%~dp0backend"

if not exist venv (
    echo [启动失败] 未找到虚拟环境，请先双击 install.bat 完成安装
    pause
    exit /b 1
)
call venv\Scripts\activate.bat

set "PORT=8000"
for /f "tokens=2 delims==" %%a in ('findstr /b BACKEND_PUBLIC_PORT= .env 2^>nul') do set PORT=%%a

echo [PyGBSentry] 启动后端 → http://localhost:%PORT%
echo [PyGBSentry] API 文档 → http://localhost:%PORT%/docs
echo [PyGBSentry] 关闭服务：在本窗口按 Ctrl+C
python -m app.main
pause
