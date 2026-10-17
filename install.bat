@echo off
REM =============================================================
REM PyGBSentry 一键安装（Windows，双击即可运行）
REM 适用：快速体验（SQLite 模式，无需 PostgreSQL / Redis / Node）
REM 安装完成后双击 start.bat 启动，浏览器打开 http://localhost:8000
REM =============================================================
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ==============================================
echo    PyGBSentry 一键安装（Windows 快速模式）
echo ==============================================
echo.

REM ---------- 1. 查找 Python（需要 3.11 ~ 3.13） ----------
echo [1/5] 检查 Python（需要 3.11 ~ 3.13）...
set "PY_BIN="
for %%P in (py python python3) do (
    if not defined PY_BIN (
        %%P -c "import sys; assert sys.version_info >= (3,11) and sys.version_info < (3,14)" >nul 2>&1 && set "PY_BIN=%%P"
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
    echo [失败] 未找到合适的 Python。当前检测：
    python --version 2>nul || echo   未安装 Python
    echo.
    echo 本项目要求 Python 3.11 ~ 3.13（3.8/3.9/3.10 无法运行，会报语法错误）。
    echo.
    echo 安装方法：
    echo   官网下载 https://www.python.org/downloads/release/python-3128/
    echo   （安装时务必勾选 Add python.exe to PATH）
    echo   国内镜像 https://mirrors.huaweicloud.com/python/
    echo.
    echo 装好后重新双击 install.bat
    pause
    exit /b 1
)
for /f "delims=" %%v in ('%PY_BIN% -c "import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")"') do set PY_VER=%%v
echo [ OK ] 找到 Python %PY_VER%

REM ---------- 2. 虚拟环境 ----------
echo [2/5] 创建虚拟环境...
cd backend
if not exist venv (
    %PY_BIN% -m venv venv
    if errorlevel 1 (
        echo [失败] 创建虚拟环境失败，请把上方报错发到 issue
        pause
        exit /b 1
    )
)
call venv\Scripts\activate.bat
echo [ OK ] 虚拟环境就绪

REM ---------- 3. 依赖 ----------
echo [3/5] 安装后端依赖（约 1-3 分钟，请耐心等待）...
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo 清华镜像失败，改用官方源重试...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [失败] 依赖安装失败，请检查网络后重试
        pause
        exit /b 1
    )
)
echo [ OK ] 依赖安装完成

REM ---------- 4. 配置 .env ----------
echo [4/5] 生成配置文件 .env ...
if exist .env (
    echo [提示] .env 已存在，保留现有配置
) else (
    copy .env.example .env >nul
    for /f %%a in ('python -c "import secrets; print(secrets.token_hex(32))"') do set SECRET_HEX=%%a
    for /f %%a in ('python -c "import secrets; print(secrets.token_hex(32))"') do set FIELD_HEX=%%a
    for /f %%a in ('python -c "import secrets; print(secrets.token_urlsafe(9))"') do set ADMIN_PWD=%%a
    powershell -NoProfile -Command ^
      "$c = Get-Content .env -Raw -Encoding UTF8;" ^
      "$c = $c -replace '(?m)^DATABASE_TYPE=postgresql','DATABASE_TYPE=sqlite';" ^
      "$c = $c -replace '(?m)^SECRET_KEY=.*',('SECRET_KEY=\"' + $env:SECRET_HEX + '\"');" ^
      "$c = $c -replace '(?m)^FIELD_ENCRYPTION_KEY=.*',('FIELD_ENCRYPTION_KEY=\"' + $env:FIELD_HEX + '\"');" ^
      "if ($c -match '(?m)^ADMIN_INITIAL_PASSWORD=') { $c = $c -replace '(?m)^ADMIN_INITIAL_PASSWORD=.*',('ADMIN_INITIAL_PASSWORD=\"' + $env:ADMIN_PWD + '\"') } else { $c += \"`nADMIN_INITIAL_PASSWORD=`\"\" + $env:ADMIN_PWD + \"`\"`n\" };" ^
      "Set-Content .env -Value $c -Encoding UTF8"
    echo [ OK ] .env 已生成（SQLite 快速模式）
)

REM ---------- 5. 初始化数据库 ----------
echo [5/5] 初始化数据库（建表 + 默认管理员）...
python app\initial_data.py
if errorlevel 1 (
    echo [失败] 数据库初始化失败，请把上方完整报错发到 issue
    pause
    exit /b 1
)
echo [ OK ] 数据库初始化完成

REM ---------- 完成 ----------
echo.
echo ==============================================
echo    安装完成！
echo ==============================================
echo.
echo   启动：      双击 start.bat（或在其窗口内按提示）
echo   访问：      http://localhost:8000/docs
echo   管理员账号：admin
for /f "tokens=2 delims==" %%a in ('findstr /b ADMIN_INITIAL_PASSWORD= .env') do echo   管理员密码：%%a
echo   （首次登录后请修改密码）
echo.
echo   生产部署（PostgreSQL/Redis/Nginx/HTTPS）：docs\INSTALL.md
echo   遇到问题：https://gitee.com/suoten/PyGBSentry/issues
echo.
pause
