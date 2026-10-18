# -*- coding: utf-8 -*-
"""
PyGBSentry Windows 便携版打包器。

产出：PyGBSentry-windows-portable.zip —— 解压到任意目录、双击 启动PyGBSentry.bat
即可运行完整平台。目标机器【无需安装 Python/Node/任何环境】（内置嵌入式 Python）。

用法（在本机已装 Python 3.11+ 且能联网的机器上执行）：
    python make_portable.py
    python make_portable.py --mirror        # 国内网络使用清华镜像
产出：dist_portable/PyGBSentry-windows-portable.zip

组成：
    PyGBSentry/
      python/            嵌入式 Python 3.12（含全部依赖，免安装）
      backend/           平台后端代码 + 插件
      frontend/dist/     预构建管理界面
      启动PyGBSentry.bat 停止PyGBSentry.bat
      说明.txt
"""
import argparse
import io
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))            # editions/open-source
REPO = os.path.dirname(HERE)                                  # editions
OUT_ROOT = os.path.join(HERE, "dist_portable")
BUILD = os.path.join(OUT_ROOT, "PyGBSentry")
PY_DIR = os.path.join(BUILD, "python")
ZIP_OUT = os.path.join(OUT_ROOT, "PyGBSentry-windows-portable.zip")

PY_EMBED_URLS = [
    "https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip",
    "https://mirrors.huaweicloud.com/python/3.12.8/python-3.12.8-embed-amd64.zip",
]
GETPIP_URLS = [
    "https://bootstrap.pypa.io/get-pip.py",
    "https://mirrors.aliyun.com/pypi/get-pip.py",
]
PIP_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"


def info(msg):
    print(f"[便携版] {msg}", flush=True)


def download(urls, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for url in urls:
        try:
            info(f"下载 {url.split('/')[2]} ...")
            urllib.request.urlretrieve(url, dest)
            return True
        except Exception as e:
            info(f"  失败：{e}，尝试下一个源")
    return False


def reset_build():
    if os.path.isdir(BUILD):
        shutil.rmtree(BUILD)
    os.makedirs(BUILD, exist_ok=True)


def setup_embed_python(mirror: bool):
    embed_zip = os.path.join(OUT_ROOT, "python-embed.zip")
    if not download(PY_EMBED_URLS, embed_zip):
        raise SystemExit("嵌入式 Python 下载失败，请检查网络后重试")
    info("解压嵌入式 Python ...")
    with zipfile.ZipFile(embed_zip) as z:
        z.extractall(PY_DIR)
    os.remove(embed_zip)

    # 启用 site-packages：编辑 python312._pth
    pth = next(f for f in os.listdir(PY_DIR) if f.endswith("._pth"))
    pth_path = os.path.join(PY_DIR, pth)
    content = io.open(pth_path, encoding="utf-8").read()
    content = content.replace("#import site", "import site\nimport sys\nsys.path.append('Lib\\\\site-packages')")
    io.open(pth_path, "w", encoding="utf-8").write(content)

    # get-pip
    getpip = os.path.join(OUT_ROOT, "get-pip.py")
    if not download(GETPIP_URLS, getpip):
        raise SystemExit("get-pip.py 下载失败")
    index = ["-i", PIP_INDEX] if mirror else []
    info("安装 pip 到嵌入式 Python ...")
    subprocess.run([os.path.join(PY_DIR, "python.exe"), getpip, "--no-warn-script-location"] + index, check=True)
    os.remove(getpip)


def install_deps(mirror: bool):
    req = os.path.join(HERE, "backend", "requirements.txt")
    index = ["-i", PIP_INDEX] if mirror else []
    info("安装平台依赖到嵌入式 Python（几分钟）...")
    subprocess.run(
        [os.path.join(PY_DIR, "python.exe"), "-m", "pip", "install", "-r", req,
         "--no-warn-script-location"] + index, check=True,
    )


def copy_payload():
    info("复制平台代码与前端 ...")
    # backend 代码（排除测试/临时）
    backend_src = os.path.join(HERE, "backend")
    backend_dst = os.path.join(BUILD, "backend")
    os.makedirs(backend_dst, exist_ok=True)
    for name in ("app", "plugins", "alembic", "alembic.ini", "requirements.txt", ".env.example"):
        src = os.path.join(backend_src, name)
        dst = os.path.join(backend_dst, name)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "venv", ".venv", "logs"))
        elif os.path.isfile(src):
            shutil.copy2(src, dst)
    # 前端 dist
    shutil.copytree(os.path.join(HERE, "frontend", "dist"), os.path.join(BUILD, "frontend", "dist"))

    # .env（SQLite 快速模式 + 随机密钥）
    import re
    import secrets
    env_example = os.path.join(backend_src, ".env.example")
    env_text = io.open(env_example, encoding="utf-8").read()
    env_text = re.sub(r"(?m)^DATABASE_TYPE=postgresql", "DATABASE_TYPE=sqlite", env_text)
    env_text = re.sub(r"(?m)^SECRET_KEY=.*", 'SECRET_KEY="' + secrets.token_hex(32) + '"', env_text)
    env_text = re.sub(r"(?m)^FIELD_ENCRYPTION_KEY=.*", 'FIELD_ENCRYPTION_KEY="' + secrets.token_hex(32) + '"', env_text)
    pwd = secrets.token_urlsafe(9)
    env_text = re.sub(r"(?m)^ADMIN_INITIAL_PASSWORD=.*", 'ADMIN_INITIAL_PASSWORD="' + pwd + '"', env_text)
    io.open(os.path.join(backend_dst, ".env"), "w", encoding="utf-8").write(env_text)
    io.open(os.path.join(BUILD, "ADMIN_PASSWORD.txt"), "w", encoding="utf-8").write(
        "PyGBSentry 管理员账号\n\n用户名: admin\n密码:   " + pwd + "\n\n请妥善保管，登录后可在平台内修改。\n")

    # 启动/停止脚本（工作目录相对自身）
    start_bat = r'''@echo off
title PyGBSentry
cd /d "%~dp0backend"
set "PORT=8000"
for /f "tokens=2 delims==" %%a in ('findstr /b BACKEND_PUBLIC_PORT= .env 2^>nul') do set PORT=%%a
netstat -ano | findstr ":%PORT% " | findstr LISTENING >nul 2>&1
if not errorlevel 1 (
    echo PyGBSentry already running - opening browser...
    start "" "http://localhost:%PORT%"
    timeout /t 2 >nul
    exit /b 0
)
start "" /min cmd /c "timeout /t 10 /nobreak >nul && start "" http://localhost:%PORT%"
echo [PyGBSentry] Starting - http://localhost:%PORT%
echo [PyGBSentry] Keep this window OPEN. Stop: double-click stop.bat
"%~dp0python\python.exe" -m app.main
pause
'''
    stop_bat = r'''@echo off
cd /d "%~dp0backend"
set "PORT=8000"
for /f "tokens=2 delims==" %%a in ('findstr /b BACKEND_PUBLIC_PORT= .env 2^>nul') do set PORT=%%a
set "SIP_PORT=5062"
for /f "tokens=2 delims==" %%a in ('findstr /b SIP_PORT= .env 2^>nul') do set SIP_PORT=%%a
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%SIP_PORT% " ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1
echo [ OK ] stopped.
timeout /t 2 >nul
'''
    readme = (
        "【PyGBSentry 便携版 —— 解压即用】\n\n"
        "1. 把整个 PyGBSentry 文件夹放到任意位置（路径建议不要含中文/空格更稳）\n"
        "2. 双击「启动PyGBSentry.bat」，浏览器会自动打开管理界面\n"
        "3. 管理员账号 admin，密码见 ADMIN_PASSWORD.txt（登录后请修改）\n"
        "4. 停止：双击「停止PyGBSentry.bat」或直接关闭启动窗口\n"
        "5. 本机无需安装 Python / Node / 数据库 —— 全部内置\n\n"
        "遇到问题：运行 doctor 检查（可运行「启动PyGBSentry.bat」前先看本目录说明），\n"
        "或到 https://gitee.com/suoten/PyGBSentry/issues 提交（附上控制台输出）。\n"
    )
    io.open(os.path.join(BUILD, "启动PyGBSentry.bat"), "w", encoding="ascii", newline="\r\n").write(start_bat)
    io.open(os.path.join(BUILD, "停止PyGBSentry.bat"), "w", encoding="ascii", newline="\r\n").write(stop_bat)
    io.open(os.path.join(BUILD, "说明.txt"), "w", encoding="utf-8-sig", newline="\r\n").write(readme)


def make_zip():
    info("压缩为 zip（约 300-500MB，需要几分钟）...")
    if os.path.isfile(ZIP_OUT):
        os.remove(ZIP_OUT)
    with zipfile.ZipFile(ZIP_OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, dirs, files in os.walk(BUILD):
            for f in files:
                full = os.path.join(root, f)
                arc = "PyGBSentry/" + os.path.relpath(full, BUILD).replace("\\", "/")
                z.write(full, arc)
    size_mb = os.path.getsize(ZIP_OUT) / 1048576
    info(f"完成：{ZIP_OUT}（{size_mb:.0f} MB）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mirror", action="store_true", help="使用清华 PyPI 镜像")
    args = ap.parse_args()
    if sys.platform != "win32":
        raise SystemExit("便携版仅支持在 Windows 上打包")
    reset_build()
    setup_embed_python(args.mirror)
    install_deps(args.mirror)
    copy_payload()
    make_zip()


if __name__ == "__main__":
    main()
