# -*- coding: utf-8 -*-
"""
PyGBSentrySetup — Windows 一键安装向导（单文件 exe，用 PyInstaller 打包）。

给"完全不懂程序"的用户：双击 exe → 点「开始安装」→ 全自动完成
  1) 检测/静默安装 Python 3.12（未装时自动下载官方安装器）
  2) 从 Gitee 下载平台源码 ZIP 并解压
  3) 创建虚拟环境 + 安装依赖（清华镜像，失败回退官方源）
  4) 生成 .env（SQLite 快速模式 + 随机密钥）+ 初始化数据库
  5) 在桌面创建「PyGBSentry」快捷方式（启动/停止）
  6) 启动平台并自动打开浏览器

无头模式（供 CI/测试）：
    PyGBSentrySetup.exe --headless --target D:\\PyGBSentry [--source <本地仓库路径>]

重新打包 exe：
    pip install pyinstaller
    pyinstaller --onefile --noconsole --name PyGBSentrySetup PyGBSentrySetup.py
"""
import argparse
import io
import os
import secrets
import shutil
import subprocess
import sys
import threading
import zipfile
import zlib
import urllib.request

APP_TITLE = "PyGBSentry 安装向导"
GITEE_ZIP = "https://gitee.com/suoten/PyGBSentry/repository/archive/master.zip"
GITHUB_ZIP = "https://github.com/suoten/PyGBSentry/archive/refs/heads/master.zip"
PYTHON_INSTALLER_URLS = [
    "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe",
    "https://mirrors.huaweicloud.com/python/3.12.8/python-3.12.8-amd64.exe",
]
TSINGHUA = ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]

_state = {"cancel": False}


# ─────────────────────────── 工具函数 ───────────────────────────
def _force_rmtree(path):
    """安装器专用强删：.git 对象/只读文件在 Windows 上需先去只读再删。"""
    import stat

    def _onerr(func, p, exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    if os.path.isdir(path):
        shutil.rmtree(path, onerror=_onerr)


def find_python():
    """返回 (python可执行文件, 版本串)；版本不符返回 (None, 当前版本串)。"""
    cands = ["python", "python3", "py"]
    local = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python312", "python.exe")
    if os.path.isfile(local):
        cands.insert(0, local)
    for c in cands:
        try:
            r = subprocess.run([c, "-c", "import sys;print(sys.version.split()[0])"],
                               capture_output=True, text=True, timeout=20)
            ver = r.stdout.strip()
            parts = ver.split(".")
            if len(parts) >= 2 and parts[0] == "3" and parts[1].isdigit() and 11 <= int(parts[1]) <= 13:
                return c, ver
            last = ver
        except Exception:
            last = "not found"
    return None, last


def install_python_silently(log):
    log("未检测到合适的 Python，正在下载 Python 3.12 官方安装器（约 25MB）...")
    dest = os.path.join(os.environ.get("TEMP", "."), "python-3.12.8-amd64.exe")
    for url in PYTHON_INSTALLER_URLS:
        try:
            urllib.request.urlretrieve(url, dest)
            break
        except Exception as e:
            log(f"下载失败（{e}），尝试下一个源...")
    else:
        raise RuntimeError("Python 安装器下载失败，请手动安装 Python 3.12 后重试")
    log("正在静默安装 Python 3.12（约 1 分钟，会自动加入 PATH）...")
    subprocess.run([dest, "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_test=0"], check=True)
    log("Python 安装完成。")


def download_repo(target_dir, log):
    """下载 Gitee master.zip 并解压，返回 open-source 目录路径。"""
    zip_path = os.path.join(os.environ.get("TEMP", "."), "PyGBSentry-master.zip")
    log("正在下载平台源码（约 200-300MB，取决于网络，请耐心等待）...")
    for url in (GITEE_ZIP, GITHUB_ZIP):
        try:
            log(f"  源：{url.split('/')[2]}")
            urllib.request.urlretrieve(url, zip_path)
            break
        except Exception as e:
            log(f"  失败：{e}")
    else:
        raise RuntimeError("源码下载失败，请检查网络后重试")
    log("解压源码 ...")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(target_dir)
    os.remove(zip_path)
    # ZIP 内根目录形如 PyGBSentry-master/，其下直接就是平台根
    entries = [e for e in os.listdir(target_dir) if os.path.isdir(os.path.join(target_dir, e))]
    inner = os.path.join(target_dir, entries[0]) if entries else target_dir
    src = os.path.join(inner, "editions", "open-source")
    if not os.path.isdir(src):
        raise RuntimeError(f"源码结构异常：未找到 editions/open-source（{inner}）")
    return src


def patch_env(backend_dir, log):
    import re
    env_path = os.path.join(backend_dir, ".env")
    shutil.copy(os.path.join(backend_dir, ".env.example"), env_path)
    secret = secrets.token_hex(32)
    field = secrets.token_hex(32)
    pwd = secrets.token_urlsafe(9)
    s = io.open(env_path, encoding="utf-8").read()
    s = re.sub(r"(?m)^DATABASE_TYPE=postgresql", "DATABASE_TYPE=sqlite", s)
    s = re.sub(r"(?m)^SECRET_KEY=.*", 'SECRET_KEY="' + secret + '"', s)
    s = re.sub(r"(?m)^FIELD_ENCRYPTION_KEY=.*", 'FIELD_ENCRYPTION_KEY="' + field + '"', s)
    s = re.sub(r"(?m)^ADMIN_INITIAL_PASSWORD=.*", 'ADMIN_INITIAL_PASSWORD="' + pwd + '"', s)
    io.open(env_path, "w", encoding="utf-8").write(s)
    io.open(os.path.join(os.path.dirname(backend_dir), "ADMIN_PASSWORD.txt"), "w", encoding="utf-8").write(
        "PyGBSentry 管理员账号\n\n用户名: admin\n密码:   " + pwd +
        "\n\n请妥善保管，登录后可在平台内修改。\n")
    log("管理员密码已生成并保存到 ADMIN_PASSWORD.txt")
    return pwd


def create_shortcuts(install_root, backend_port, log):
    """桌面快捷方式：启动（后台服务+自动开浏览器）。"""
    desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
    if not os.path.isdir(desktop):
        desktop = os.path.join(os.environ.get("USERPROFILE", ""), "OneDrive", "Desktop")
    start_bat = os.path.join(install_root, "start.bat")
    if not os.path.isfile(desktop + r"\PyGBSentry.lnk") and os.path.isdir(desktop):
        ps = (
            "$ws = New-Object -ComObject WScript.Shell; "
            f"$lnk = $ws.CreateShortcut('{desktop}\\PyGBSentry.lnk'); "
            f"$lnk.TargetPath = '{start_bat}'; "
            "$lnk.Save()"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)
        log("已创建桌面快捷方式：PyGBSentry")


def run_install(src_dir, target_dir, py_bin, log):
    """安装主流程。

    顺序关键：①源码先就位到最终目录再建 venv（venv 记录绝对路径）；
    ②venv 必须用真实 Python 的 `-m venv` 创建——从 PyInstaller exe 运行时
    sys.executable 是 exe 自己，venv.create 会把 exe 当基础解释器（致命）。
    """

    # 就位：把 open-source 目录移到 <target>/PyGBSentry
    final_dir = os.path.join(target_dir, "PyGBSentry")
    if os.path.abspath(src_dir) != os.path.abspath(final_dir):
        log("就位安装文件 ...")
        if os.path.isdir(final_dir):
            _force_rmtree(final_dir)
        try:
            # 同盘：rename 瞬间完成
            shutil.move(src_dir, final_dir)
        except OSError:
            # 跨盘/占用：过滤复制（排除 .git/开发产物；.git 里的 pack 文件常被占用）。
            # dirs_exist_ok 容忍 rename 失败时残留的目标目录（Windows 句柄占用场景）
            log("复制安装文件（已排除 .git 与开发产物，约 1-2 分钟）...")
            ignore = shutil.ignore_patterns(
                ".git", ".git_broken_backup", ".showreel", "node_modules", "__pycache__", "htmlcov",
                "logs", "*.db", "*.db-wal", "*.db-shm", "dist_portable",
                "bilibili_publish.txt", "init_script.js",
            )
            shutil.copytree(src_dir, final_dir, ignore=ignore, dirs_exist_ok=True)
            log("复制完成，清理临时源目录 ...")
            _force_rmtree(src_dir)

    backend = os.path.join(final_dir, "backend")
    venv_dir = os.path.join(backend, "venv")
    log("创建虚拟环境（在最终安装位置，避免路径失效）...")
    subprocess.run([py_bin, "-m", "venv", venv_dir], check=True)
    vpy = os.path.join(venv_dir, "Scripts", "python.exe")

    log("安装后端依赖（清华镜像，约 1-3 分钟）...")
    r = subprocess.run([vpy, "-m", "pip", "install", "-r", "requirements.txt"] + TSINGHUA,
                       cwd=backend, capture_output=True, text=True)
    if r.returncode != 0:
        log("清华镜像失败，改用官方源重试 ...")
        r = subprocess.run([vpy, "-m", "pip", "install", "-r", "requirements.txt"],
                           cwd=backend, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("依赖安装失败：\n" + (r.stderr or "")[-800:])

    log("生成配置与初始化数据库 ...")
    patch_env(backend, log)
    r = subprocess.run([vpy, "-m", "app.initial_data"], cwd=backend, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("数据库初始化失败：\n" + (r.stderr or "")[-800:])

    create_shortcuts(final_dir, None, log)

    log("启动平台 ...")
    # FIXED: [2026-10-18] 多层引号转义在 cmd 里不可靠——生成 bat 再启动
    launcher = os.path.join(os.path.dirname(backend), "启动PyGBSentry.bat")
    bat = ('@echo off' + chr(13) + chr(10) +
            'title PyGBSentry' + chr(13) + chr(10) +
            'cd /d "%~dp0backend"' + chr(13) + chr(10) +
            'venv\\Scripts\\python.exe -m app.main' + chr(13) + chr(10) +
            'pause' + chr(13) + chr(10)
    )
    io.open(launcher, "w", encoding="ascii", newline="").write(bat)
    stopper = os.path.join(os.path.dirname(backend), "停止PyGBSentry.bat")
    bat = ('@echo off' + chr(13) + chr(10) +
            'cd /d "%~dp0backend"' + chr(13) + chr(10) +
            'set PORT=8000' + chr(13) + chr(10) +
            "for /f \"tokens=2 delims==\" %a in ('findstr /b BACKEND_PUBLIC_PORT= .env 2^>nul') do set PORT=%a" + chr(13) + chr(10) +
            "for /f \"tokens=5\" %p in ('netstat -ano ^| findstr :%PORT% ^| findstr LISTENING') do taskkill /PID %p /F" + chr(13) + chr(10) +
            'echo stopped' + chr(13) + chr(10)
    )
    io.open(stopper, "w", encoding="ascii", newline="").write(bat)
    subprocess.Popen(["cmd", "/c", "start", "", launcher], shell=True)
    port = "8000"
    ef = os.path.join(backend, ".env")
    if os.path.isfile(ef):
        import re as _re
        m = _re.search(r"(?m)^BACKEND_PUBLIC_PORT=(\d+)", io.open(ef, encoding="utf-8").read())
        if m:
            port = m.group(1)
    log(f"安装完成！浏览器将自动打开 http://localhost:{port}")
    log(f"管理员账号 admin，密码见 {os.path.join(final_dir, 'ADMIN_PASSWORD.txt')}")
    try:
        import webbrowser
        import time as _t
        _t.sleep(6)
        webbrowser.open(f"http://localhost:{port}")
    except Exception:
        pass


# ─────────────────────────── GUI ───────────────────────────
def run_gui(target_dir):
    import tkinter as tk
    from tkinter import scrolledtext

    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("640x420")
    root.resizable(False, False)

    tk.Label(root, text="PyGBSentry 一键安装", font=("Microsoft YaHei", 16, "bold")).pack(pady=(18, 4))
    tk.Label(root, text="全自动：环境检测 → 下载源码 → 安装依赖 → 桌面快捷方式 → 自动启动\n"
                        "安装目录：" + target_dir,
             justify="center", fg="#555").pack(pady=4)

    logbox = scrolledtext.ScrolledText(root, width=76, height=16, state="disabled", font=("Consolas", 9))
    logbox.pack(padx=14, pady=10)

    def log(msg):
        logbox.configure(state="normal")
        logbox.insert("end", msg + "\n")
        logbox.see("end")
        logbox.configure(state="disabled")
        root.update_idletasks()

    btn = tk.Button(root, text="开 始 安 装", font=("Microsoft YaHei", 12, "bold"),
                    width=22, height=2, bg="#2563eb", fg="white")

    def worker():
        try:
            py, ver = find_python()
            if py is None:
                install_python_silently(log)
                py, ver = find_python()
                if py is None:
                    raise RuntimeError("Python 安装后仍未检测到，请重启电脑后再运行本向导。")
            log(f"Python {ver} 就绪")
            if os.path.isdir(target_dir) and os.listdir(target_dir):
                raise RuntimeError(f"安装目录已存在且非空：{target_dir}\n请删除后重试，或换一个目录。")
            os.makedirs(target_dir, exist_ok=True)
            src = download_repo(target_dir, log)
            run_install(src, target_dir, py, log)
            btn.configure(text="✔ 安装完成", bg="#16a34a", state="disabled")
        except Exception as e:
            log("\n[安装失败] " + str(e))
            log("请截图本窗口全部内容，到 https://gitee.com/suoten/PyGBSentry/issues 提问。")
            btn.configure(text="✖ 安装失败", bg="#dc2626", state="disabled")

    def on_start():
        btn.configure(state="disabled", text="安装中...")
        threading.Thread(target=worker, daemon=True).start()

    btn.configure(command=on_start)
    btn.pack(pady=(0, 14))
    root.mainloop()


# ─────────────────────────── 无头模式 ───────────────────────────
def run_headless(args):
    def log(msg):
        print(msg, flush=True)

    py, ver = find_python()
    if py is None and args.skip_python_check:
        py = "python"  # 回退 PATH 命令名（后续 -m venv/pip 均经由真实解释器）
    if py is None:
        raise SystemExit("未检测到 Python 3.11-3.13（headless 模式不自动安装，请手动安装）")
    log(f"Python 就绪：{py} ({ver})")

    target = args.target
    os.makedirs(target, exist_ok=True)
    if args.source:
        log(f"[skip download] 使用本地源码：{args.source}")
        src = args.source
        run_install(src, target, py, log)
    else:
        src = download_repo(target, log)
        run_install(src, target, py, log)
    print("HEADLESS OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--target", default=os.path.join(os.environ.get("SYSTEMDRIVE", "C:") + "\\", "PyGBSentry"))
    ap.add_argument("--source", default=None, help="使用本地源码目录（跳过下载，测试用）")
    ap.add_argument("--skip-python-check", action="store_true")
    args = ap.parse_args()

    if args.headless:
        run_headless(args)
    else:
        run_gui(args.target)


if __name__ == "__main__":
    main()
