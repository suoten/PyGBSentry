import os
import sys
import platform
import subprocess
import configparser
import asyncio
import time
import zipfile
import tarfile
import shutil
import threading
import socket
import io
import contextlib
from pathlib import Path
from urllib import request as urllib_request, parse as urllib_parse
from loguru import logger
from app.core.config import settings
from app.core.archive import safe_extract_zip, safe_extract_tar, UnsafeArchiveError
# P0-16 [2026-07-17]: 使用项目统一的 fire_and_forget 替代裸 create_task
from app.core.async_utils import fire_and_forget
from app.db.session import AsyncSessionLocal
from app.core.media_nodes_db import get_active_media_node_id, get_db_media_node_by_id, select_best_db_node
from app.models.media_node import MediaNode
from sqlalchemy import func, or_, select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入

# 重要说明：
# 官方仓库 https://github.com/ZLMediaKit/ZLMediaKit 当前没有 GitHub Releases（无“最新预编译包”可直接下载）。
# 因此“每次下载最新官方版本”在开源版里只能走：下载最新源码 + 本机编译。
# 开源版这里默认只支持 Linux 自动部署（Windows 自动部署容易受编译环境影响，且你已明确不考虑）。
ZLM_OFFICIAL_SOURCE_ZIP_URL = "https://github.com/ZLMediaKit/ZLMediaKit/archive/refs/heads/master.zip"
ZLM_SOURCE_ZIP_URL_ENV = "ZLM_SOURCE_ZIP_URL"
ZLM_ZLTOOLKIT_ZIP_URL_ENV = "ZLM_ZLTOOLKIT_ZIP_URL"
ZLM_GIT_URL_ENV = "ZLM_GIT_URL"
ZLM_GIT_REF_ENV = "ZLM_GIT_REF"

# FIX [2026-07-22 P1]: ZLM 下载镜像列表（GitHub 官方 + Gitee 镜像）。
# GitHub 在国内下载极慢甚至超时，Gitee 镜像（作者 xia-chu 官方同步）国内可达性好。
# 用户未显式配置 ZLM_GIT_URL / ZLM_SOURCE_ZIP_URL / ZLM_ZLTOOLKIT_ZIP_URL 时，
# 并发探测各镜像首字节延迟，自动选择最快的源（可通过 ZLM_MIRROR_AUTO_SELECT=false 关闭）。
ZLM_GIT_URL_MIRRORS = [
    "https://gitee.com/xia-chu/ZLMediaKit.git",
    "https://github.com/ZLMediaKit/ZLMediaKit.git",
]
ZLM_SOURCE_ZIP_MIRRORS = [
    "https://gitee.com/xia-chu/ZLMediaKit/repository/archive/master.zip",
    ZLM_OFFICIAL_SOURCE_ZIP_URL,
]
ZLM_ZLTOOLKIT_ZIP_MIRRORS = [
    "https://gitee.com/xia-chu/ZLToolKit/repository/archive/master.zip",
    "https://github.com/ZLMediaKit/ZLToolKit/archive/refs/heads/master.zip",
]

# 可选兜底：若你自己维护了预编译包下载地址，可通过环境变量显式开启：
# - ZLM_FALLBACK_BINARY_URL (例如 https://.../ZLMediaKit-linux64.tar.gz 或 .zip)
# 默认关闭，避免指向不存在的链接导致“看似自动部署但实际失败”。

class MediaManager:
    def _normalize_rtp_port_range(self, raw: str | None, fallback_port: int) -> str:
        text = str(raw or "").strip()
        start = 0
        end = 0
        if "-" in text:
            try:
                left, right = text.split("-", 1)
                start = int(left.strip() or 0)
                end = int(right.strip() or 0)
            except Exception:
                start = 0
                end = 0
        if start <= 0:
            start = int(fallback_port or 30000)
        start = max(1, min(65535, start))
        min_end = start + 35
        if end < min_end:
            end = min_end
        if end > 65535:
            end = 65535
            start = max(1, end - 35)

        if self._is_running_in_docker():
            max_ports = int(os.environ.get("DOCKER_RTP_PORT_RANGE_MAX", "200") or "200")
            max_ports = max(36, min(max_ports, 9000))
            if (end - start + 1) > max_ports:
                original_end = end
                end = start + max_ports - 1
                logger.warning(
                    "Docker environment: RTP port range too large ({}-{}, {} ports), "
                    "auto-capped to {}-{} ({} ports, DOCKER_RTP_PORT_RANGE_MAX={}). "
                    "Ensure docker-compose.yml maps the same range.",
                    start, original_end, original_end - start + 1,
                    start, end, max_ports, max_ports,
                )

        self._effective_rtp_range = (start, end)
        normalized = f"{start}-{end}"
        if text != normalized:
            logger.warning("Normalize ZLM rtp_proxy.port_range from '{}' to '{}'", text or "(empty)", normalized)
        return normalized

    def _is_loopback_host(self, value: str | None) -> bool:
        host = str(value or "").strip().lower()
        return host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}

    def _is_loopback_url(self, value: str | None) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        try:
            parsed = urllib_parse.urlparse(text)
            return self._is_loopback_host(parsed.hostname)
        except Exception:
            return False

    @staticmethod
    def _is_running_in_docker() -> bool:
        try:
            if os.path.exists("/.dockerenv"):
                return True
        except Exception as e:
            logger.warning(f"Failed to detect Docker environment: {e}")
        return os.environ.get("RUNNING_IN_DOCKER", "").strip().lower() == "true"

    @staticmethod
    def _detect_docker_gateway_ip() -> str | None:
        # FIX [2026-07-19 P2-3]: Windows/macOS 没有 /proc/net/route，
        # 跳过 Docker 网关探测，避免 FileNotFoundError 刷屏 WARNING（aa.txt P2-3）。
        # 仅在 Linux 上尝试读取 /proc/net/route。
        if sys.platform not in ("linux", "cygwin"):
            return None
        try:
            with open("/proc/net/route", "r") as f:
                for line in f:
                    fields = line.strip().split()
                    if len(fields) >= 3 and fields[1] == "00000000":
                        hex_ip = fields[2]
                        if len(hex_ip) == 8:
                            octets = [str(int(hex_ip[i:i+2], 16)) for i in range(6, -1, -2)]
                            return ".".join(octets)
        except Exception as e:
            logger.warning(f"Failed to detect Docker gateway IP: {e}")
        return None

    def _ensure_hook_suffix(self, base_url: str) -> str:
        """确保 webhook base URL 包含 /api/v1/hook 后缀。

        FIX: [2026-07-16] 用户配置 MEDIA_SERVER_HOOK_BASE_URL=http://127.0.0.1:8000 时，
        缺少 /api/v1/hook 后缀导致 ZLM 回调 404。DB 中 hook_base_url 同理。
        """
        if not base_url:
            return base_url
        base_url = base_url.rstrip("/")
        api_v1_str = str(settings.API_V1_STR or "/api/v1")
        hook_suffix = f"{api_v1_str}/hook"
        if not base_url.endswith(hook_suffix):
            base_url = f"{base_url}{hook_suffix}"
        return base_url

    def _resolve_webhook_base(self, node: dict | None) -> str:
        # FIX: [2026-07-14] 内置 ZLM 与后端在同一服务器上，后端在生产环境绑定 127.0.0.1，
        # ZLM 必须通过 127.0.0.1 回调后端。使用公网域名会导致 connection refused，
        # 因为后端不监听公网接口（仅通过 nginx 反向代理对外提供服务）。
        # Docker 环境下 127.0.0.1 不可达（ZLM 与后端在不同容器），需走容器网关 IP。
        is_embedded_zlm = bool(getattr(self, "zlm_path", "") or "")
        if is_embedded_zlm and not self._is_running_in_docker():
            # 优先使用用户显式配置的 MEDIA_SERVER_HOOK_BASE_URL（包括 loopback URL）
            global_base = str(settings.MEDIA_SERVER_HOOK_BASE_URL or "").strip()
            if global_base:
                return self._ensure_hook_suffix(global_base)
            # 默认使用 127.0.0.1 回调后端，确保在生产环境（绑定 127.0.0.1）下可达
            return f"http://127.0.0.1:{settings.BACKEND_PUBLIC_PORT}{settings.API_V1_STR}/hook"

        hook_base = str((node or {}).get("hook_base_url") or "").strip()
        is_node_embedded = bool((node or {}).get("is_embedded"))
        if hook_base:
            # FIX: [2026-07-16] 内置 ZLM 节点的 loopback hook_base_url 是正确的（ZLM 与后端同机），
            # 不应跳过。只有外置节点才需要跳过 loopback URL。
            if is_node_embedded:
                return self._ensure_hook_suffix(hook_base)
            if not self._is_loopback_url(hook_base):
                return self._ensure_hook_suffix(hook_base)

        hook_ip = str((node or {}).get("hook_ip") or "").strip()
        if hook_ip:
            if is_node_embedded or not self._is_loopback_host(hook_ip):
                return f"http://{hook_ip}:{settings.BACKEND_PUBLIC_PORT}{settings.API_V1_STR}/hook"

        node_ip = str((node or {}).get("ip") or "").strip()
        if node_ip:
            if is_node_embedded or not self._is_loopback_host(node_ip):
                return f"http://{node_ip}:{settings.BACKEND_PUBLIC_PORT}{settings.API_V1_STR}/hook"

        global_base = str(settings.MEDIA_SERVER_HOOK_BASE_URL or "").strip()
        if global_base:
            # FIX: [2026-07-16] 内置 ZLM 节点允许 loopback URL（ZLM 与后端同机）
            if is_node_embedded or not self._is_loopback_url(global_base):
                return self._ensure_hook_suffix(global_base)

        backend_host = str(settings.BACKEND_PUBLIC_HOST or "").strip()
        if backend_host and not self._is_loopback_host(backend_host):
            return f"http://{backend_host}:{settings.BACKEND_PUBLIC_PORT}{settings.API_V1_STR}/hook"

        media_host = str(settings.MEDIA_SERVER_HOST or "").strip()
        if media_host and not self._is_loopback_host(media_host):
            return f"http://{media_host}:{settings.BACKEND_PUBLIC_PORT}{settings.API_V1_STR}/hook"

        # Docker 环境下 loopback 地址不可达（ZLM 与后端在不同容器），尝试自动检测容器网关 IP
        if self._is_running_in_docker():
            gateway_ip = self._detect_docker_gateway_ip()
            if gateway_ip:
                logger.info(
                    "Docker environment detected: BACKEND_PUBLIC_HOST is loopback, "
                    f"auto-detected container gateway IP={gateway_ip} for ZLM webhook"
                )
                return f"http://{gateway_ip}:{settings.BACKEND_PUBLIC_PORT}{settings.API_V1_STR}/hook"
            else:
                logger.error(
                    "Docker environment detected but cannot detect gateway IP. "
                    "ZLM webhook will be unreachable! Please set BACKEND_PUBLIC_HOST to a reachable IP in .env"
                )

        return f"http://{settings.BACKEND_PUBLIC_HOST}:{settings.BACKEND_PUBLIC_PORT}{settings.API_V1_STR}/hook"

    def _warn_if_ffmpeg_missing(self) -> None:
        try:
            if bool(getattr(self, "_ffmpeg_warned", False)):
                return
            setattr(self, "_ffmpeg_warned", True)
        except Exception as e:
            logger.warning(f"Failed to set ffmpeg warning flag: {e}")
        try:
            if shutil.which("ffmpeg"):
                return
        except Exception as e:
            logger.warning(f"Failed to check ffmpeg existence: {e}")
        logger.warning(
            "ffmpeg not found in PATH. Some features (record/convert/snapshot) may not work. "
            "Install via: sudo bash scripts/install_ffmpeg.sh (or install system ffmpeg package)."
        )

    async def _detect_external_media_nodes_configured(self) -> dict:
        """
        判断是否配置了外置媒体节点（命中则优先使用外置，不启动内置 ZLM）：
        - DB: media_nodes 表存在 is_embedded != True 的节点
        - ENV: MEDIA_NODES 非空
        """
        info = {
            "has_external": False,
            "env_media_nodes": False,
            "db_media_nodes": False,
            "db_media_nodes_count": 0,
            "active_media_node_id": None,
        }

        try:
            env_nodes = (settings.MEDIA_NODES or "").strip()
            info["env_media_nodes"] = bool(env_nodes)
        except Exception:
            info["env_media_nodes"] = False

        try:
            async with AsyncSessionLocal() as session:
                try:
                    info["active_media_node_id"] = await get_active_media_node_id(session)
                except Exception:
                    info["active_media_node_id"] = None

                result = await session.execute(
                    select(func.count(MediaNode.id)).where(
                        or_(MediaNode.is_embedded.is_(False), MediaNode.is_embedded.is_(None))
                    )
                )
                cnt = int(result.scalar() or 0)
                info["db_media_nodes_count"] = cnt
                info["db_media_nodes"] = cnt > 0
        except Exception:
            # DB 异常不应阻塞服务启动流程；只影响“是否命中外置节点”的判断精度
            info["db_media_nodes"] = False
            info["db_media_nodes_count"] = 0

        info["has_external"] = bool(info["env_media_nodes"] or info["db_media_nodes"])
        return info

    def __init__(self):
        self.process = None
        self.zlm_path = ""
        self.config_path = ""
        # W-15 _effective_rtp_range 未初始化 — 在 __init__ 中初始化为 None，访问时检查
        self._effective_rtp_range: tuple[int, int] | None = None
        if settings.EMBEDDED_ZLM_ENABLED:
            try:
                self.zlm_path = self._get_zlm_path()
                self.config_path = os.path.join(os.path.dirname(self.zlm_path), "config.ini")
            except NotImplementedError as e:
                logger.warning(str(e))
                self.zlm_path = ""
                self.config_path = ""
        # FIX: [2026-07-14] _running 初始值应为 True — start() 中 `if not self._running: return`
        # 用于防止 stop() 后重启，但初始 False 会导致 start() 永远提前返回，ZLM 无法启动。
        self._running = True
        self._stdout_thread: threading.Thread | None = None
        self._stdout_stop = threading.Event()
        self._embed_zlm_deploy_exhausted = False
        self._deploy_start_task = None
        self._restart_count = 0
        self._monitor_task = None
        self._probe_task = None
        self._register_cleanup_handlers()

    def _register_cleanup_handlers(self) -> None:
        """Register atexit and signal handlers to ensure ZLM subprocess is cleaned up on unexpected exit."""
        import atexit
        import signal

        _instance = self

        def _sync_stop():
            """Synchronous wrapper — kills ZLM subprocess on ungraceful termination."""
            try:
                if _instance.process and _instance.process.poll() is None:
                    logger.info("[cleanup] Killing orphaned ZLM subprocess (PID={})...", _instance.process.pid)
                    _instance.process.kill()
                    _instance.process.wait(timeout=3)
                    logger.info("[cleanup] ZLM subprocess killed.")
            except Exception as e:
                logger.warning(f"Exception: {e}")

        def _signal_handler(signum, frame):
            try:
                if _instance.process and _instance.process.poll() is None:
                    logger.info(f"[signal:{signum}] Terminating ZLM subprocess (PID={_instance.process.pid})...")
                    _instance.process.terminate()
                    _instance.process.wait(timeout=3)
            except Exception as e:
                logger.warning(f"Exception: {e}")

        atexit.register(_sync_stop)
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, _signal_handler)
            except (ValueError, OSError) as e:
                logger.warning(f"(ValueError, OSError): {e}")

    def _get_zlm_path(self):
        """
        Detect OS and return the path to the embedded ZLMediaKit binary
        """
        system = platform.system()
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        bin_dir = os.path.join(base_dir, "binaries")

        if system == "Linux":
            return os.path.join(bin_dir, "linux64", "MediaServer")

        # Windows/macOS 不做内置二进制包分发
        logger.info(f"ℹ️  内置 ZLMediaKit (MediaServer) 自动部署不包含 {system} 版本。")
        logger.info("   如果你在 Windows/macOS 开发，请手动下载 ZLMediaKit 并在后台运行，流媒体依然可正常接入。")

        # 返回空字符串，不抛出崩溃异常，让平台继续启动（以外置节点模式运行）
        return ""

    def _get_source_dirs(self) -> tuple[str, str]:
        """返回 (src_dir, build_dir)"""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        bin_dir = os.path.join(base_dir, "binaries")
        src_dir = os.path.join(bin_dir, "zlm_src")
        build_dir = os.path.join(bin_dir, "zlm_build")
        return src_dir, build_dir

    async def _download_package(self, url: str, dest_file: str) -> None:
        import requests

        max_seconds = max(30, int(settings.ZLM_DOWNLOAD_MAX_SECONDS or 300))

        def _download_with_progress():
            # FIX [2026-07-22 P1]: 断点续传 — 目标文件已存在时携带 Range 头从断点继续，
            # 避免低速网络下每次重试都从 0 开始（服务器重启后前次进度全部作废，永远下载不完）。
            resume_from = 0
            headers = {}
            if os.path.exists(dest_file):
                try:
                    resume_from = os.path.getsize(dest_file)
                except OSError:
                    resume_from = 0
            if resume_from > 0:
                headers["Range"] = f"bytes={resume_from}-"

            # FIX [2026-07-22 P1]: 读超时从 300s 收紧到 60s（停滞 60s 即失败），
            # 并增加总时长上限（ZLM_DOWNLOAD_MAX_SECONDS，默认 300s），
            # 防止低速 trickle 下载无限挂起、长期占用启动/部署链路。
            r = requests.get(url, stream=True, timeout=(10, 60), headers=headers)
            if r.status_code == 416:
                # 本地文件已完整（或大于远端），Range 越界：删除本地文件从头下载
                r.close()
                logger.warning("HTTP 416 on resume; local file size invalid, restarting download from scratch.")
                try:
                    os.remove(dest_file)
                except OSError:
                    pass
                resume_from = 0
                r = requests.get(url, stream=True, timeout=(10, 60))
            with r:
                mode = "wb"
                downloaded = 0
                if resume_from > 0 and r.status_code == 206:
                    # 服务器支持 Range，从断点追加
                    mode = "ab"
                    downloaded = resume_from
                    logger.info(f"Resuming download from {resume_from / (1024 * 1024):.1f} MB (HTTP 206).")
                # 200 = 服务器忽略 Range（或首次下载），从头覆盖写入
                r.raise_for_status()
                total = int(r.headers.get("content-length") or 0)
                if total > 0:
                    total += downloaded  # content-length 为剩余字节数，换算为文件总大小
                start_ts = time.time()
                last_log_ts = 0.0
                last_logged_pct = -1

                with open(dest_file, mode) as f:
                    for chunk in r.iter_content(chunk_size=1024 * 256):  # 256KB
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)

                        # 总时长上限：超时即中止（保留已下载部分供下次断点续传）
                        elapsed_total = time.time() - start_ts
                        if elapsed_total > max_seconds:
                            raise RuntimeError(
                                f"ZLM package download exceeded max duration ({max_seconds}s, "
                                f"got {downloaded / (1024 * 1024):.1f} MB). "
                                f"Partial file kept for resume; consider setting ZLM_SOURCE_ZIP_URL / "
                                f"ZLM_FALLBACK_BINARY_URL to a reachable mirror."
                            )

                        now = time.time()
                        if total > 0:
                            pct = int(downloaded * 100 / total)
                            if pct >= last_logged_pct + 5 or (now - last_log_ts) >= 5:
                                elapsed = max(now - start_ts, 0.001)
                                speed = downloaded / elapsed  # bytes/s
                                logger.info(
                                    "Downloading... {}% ({} / {} MB) ~{:.1f} MB/s",
                                    pct,
                                    f"{downloaded / (1024 * 1024):.1f}",
                                    f"{total / (1024 * 1024):.1f}",
                                    speed / (1024 * 1024),
                                )
                                last_logged_pct = pct
                                last_log_ts = now
                        else:
                            if (now - last_log_ts) >= 5:
                                elapsed = max(now - start_ts, 0.001)
                                speed = downloaded / elapsed
                                logger.info(
                                    "Downloading... {} MB ~{:.1f} MB/s",
                                    f"{downloaded / (1024 * 1024):.1f}",
                                    speed / (1024 * 1024),
                                )
                                last_log_ts = now

            # 收尾日志
            elapsed = max(time.time() - start_ts, 0.001)
            logger.info(
                "Download finished: {} MB in {:.1f}s (~{:.1f} MB/s)",
                f"{downloaded / (1024 * 1024):.1f}",
                elapsed,
                (downloaded / elapsed) / (1024 * 1024),
            )

        # 添加try-except，下载失败时抛出明确错误而非让异常泄露
        try:
            await asyncio.get_running_loop().run_in_executor(None, _download_with_progress)
        except Exception as e:
            raise RuntimeError(f"ZLM package download failed: {e}") from e

    def _run_cmd_stream(self, cmd: list[str], cwd: str | None = None, env: dict[str, str] | None = None, timeout: int = 300, prefix: str = "cmd") -> None:
        """
        以流式方式执行命令并把 stdout/stderr 实时写入日志，避免“看起来卡住”。
        """
        start_ts = time.time()
        last_line_ts = start_ts
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        try:
            assert proc.stdout is not None
            while True:
                line = proc.stdout.readline()
                now = time.time()
                if line:
                    last_line_ts = now
                    logger.info("[{}] {}", prefix, line.rstrip())
                else:
                    # 无输出时也给心跳，方便判断还在跑
                    if (now - last_line_ts) >= 10:
                        logger.info("[{}] ... running ({}s)", prefix, int(now - start_ts))
                        last_line_ts = now
                    if proc.poll() is not None:
                        break
                    time.sleep(0.2)

                if timeout and (now - start_ts) > timeout:
                    try:
                        proc.kill()
                    except Exception as e:
                        logger.warning(f"Failed to kill timed-out process: {e}")
                    raise TimeoutError(f"{prefix} timeout after {timeout}s: {' '.join(cmd)}")
        finally:
            try:
                if proc.stdout:
                    proc.stdout.close()
            except Exception as e:
                logger.warning(f"Failed to close process stdout: {e}")

        code = proc.poll()
        if code != 0:
            raise subprocess.CalledProcessError(code, cmd)

    def _estimate_build_jobs(self) -> int:
        """
        根据 CPU/内存估算一个安全的并发度，避免打满 4C8G 这类机器。
        经验：C++ 全量编译会非常吃内存；8G 建议 1~2，16G 建议 2~4。
        """
        cpu = os.cpu_count() or 1
        mem_gb = 0
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        mem_gb = max(0, int(kb / 1024 / 1024))
                        break
        except Exception:
            mem_gb = 0

        # 内存约束：每个 job 预留约 2.5GB（保守）
        if mem_gb > 0:
            mem_cap = max(1, int(mem_gb / 3))  # 8G -> 2, 16G -> 5
        else:
            mem_cap = 2

        jobs = min(cpu, mem_cap)
        # 再保守一点：最多 4，避免 gcc 链接阶段峰值
        jobs = max(1, min(jobs, 4))
        return jobs

    def _is_tcp_port_free(self, port: int) -> bool:
        if port <= 0:
            return True
        # 依次尝试 IPv6/IPv4 绑定；任一失败则认为被占用/不可用
        #
        # 注意：这里不要设置 SO_REUSEADDR。
        # 在部分系统/配置下，SO_REUSEADDR 可能导致“已被占用的端口仍可 bind 成功”的误判，
        # 进而回退逻辑失效（典型表现：443 实际被占用，但仍写入 sslport=443，ZLM 启动时报 address already in use）。
        for family, addr in ((socket.AF_INET6, ("::", port)), (socket.AF_INET, ("0.0.0.0", port))):
            s = None
            try:
                s = socket.socket(family, socket.SOCK_STREAM)
                # 避免双栈行为导致误判：IPv6 检测时显式启用 v6only
                if family == socket.AF_INET6:
                    try:
                        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                    except Exception as e:
                        logger.warning(f"Failed to set socket option: {e}")
                s.bind(addr)
                # 仅 bind 在少数环境下可能误判，这里补一次 listen 更接近真实“占用”语义
                s.listen(1)
            except OSError:
                return False
            finally:
                try:
                    if s is not None:
                        s.close()
                except Exception as e:
                    logger.warning(f"Failed to close socket: {e}")
        return True

    def _pick_free_port(self, preferred: int, fallback_start: int, fallback_end: int) -> int:
        if preferred > 0 and self._is_tcp_port_free(preferred):
            return preferred

        strategy = str(settings.ZLM_FALLBACK_PORT_STRATEGY or "nearby").strip().lower()
        offsets_raw = str(settings.ZLM_FALLBACK_PORT_OFFSETS or "").strip()
        offsets: list[int] = []
        if offsets_raw:
            for part in offsets_raw.split(","):
                try:
                    v = int(part.strip())
                    if v != 0:
                        offsets.append(v)
                except Exception:
                    continue
        if not offsets:
            offsets = [1, 2, 3, 10, 100, 200, 500, 1000]

        # 1) nearby：优先尝试“离原端口近”的候选，特别适合 443 -> 543 这种诉求
        if strategy in {"nearby", "auto"} and preferred > 0:
            for off in offsets:
                cand = preferred + off
                if 1 <= cand <= 65535 and self._is_tcp_port_free(cand):
                    return cand

        # 2) range：最后兜底，避免完全找不到端口
        start = max(1, int(fallback_start or 18000))
        end = max(start, int(fallback_end or 18999))
        for p in range(start, end + 1):
            if self._is_tcp_port_free(p):
                return p
        return preferred

    _PROTECTED_PROCESS_NAMES = {"nginx", "apache2", "httpd", "mysqld", "postgres", "redis-server", "docker", "containerd", "sshd", "systemd", "init"}

    async def _ensure_port_free(self, port: int) -> None:
        """确保端口空闲，必要时终止占用进程。

        FIX [2026-07-19]: 改为 async 方法，用 asyncio.sleep 替代 time.sleep，
        避免阻塞事件循环（Bug4: Event loop blocking）。
        psutil.net_connections() 仍是同步阻塞调用，但通常 <100ms，可接受；
        未来可考虑移到 executor 中执行。
        """
        if port <= 0:
            return
        if self._is_tcp_port_free(port):
            return

        import psutil
        logger.warning(f"Port {port} is occupied, attempting to terminate the occupying process...")
        killed = False
        try:
            for conn in psutil.net_connections(kind='tcp'):
                if conn.laddr and conn.laddr.port == port and conn.status == 'LISTEN':
                    if conn.pid:
                        try:
                            p = psutil.Process(conn.pid)
                            if p.pid == os.getpid():
                                continue
                            proc_name = (p.name() or "").lower()
                            if proc_name in self._PROTECTED_PROCESS_NAMES:
                                logger.warning(f"Skipping protected process {proc_name} (PID: {p.pid}) on port {port}, will use fallback port instead")
                                continue
                            logger.info(f"Terminating process {p.name()} (PID: {p.pid}) on port {port}...")
                            p.terminate()
                            p.wait(timeout=3)
                            killed = True
                        except psutil.TimeoutExpired:
                            logger.warning(f"Process {conn.pid} did not terminate in time, using kill()...")
                            p.kill()
                            p.wait(timeout=3)
                            killed = True
                        except psutil.NoSuchProcess:
                            killed = True
                        except Exception as e:
                            logger.error(f"Failed to kill process {conn.pid} on port {port}: {e}")
                    else:
                        logger.error(f"Port {port} is occupied, but PID could not be determined (requires root privileges).")
        except psutil.AccessDenied:
            logger.error(f"Access denied while scanning network connections for port {port}. Are you running as root?")
        except Exception as e:
            logger.error(f"Failed to scan network connections for port {port}: {e}")

        if killed:
            # FIX [2026-07-19]: 使用 asyncio.sleep 替代 time.sleep，避免阻塞事件循环
            await asyncio.sleep(1)

    def _get_system_resources(self) -> tuple[int, int]:
        """返回 (cpu_count, mem_gb)。mem_gb 读取失败则为 0。"""
        cpu = os.cpu_count() or 1
        mem_gb = 0
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        mem_gb = max(0, int(kb / 1024 / 1024))
                        break
        except Exception:
            mem_gb = 0
        return cpu, mem_gb

    def _warn_if_zlm_webrtc_disabled_in_cache(self, build_dir: str) -> None:
        """
        ZLMediaKit：Not found OpenSSL 或 libsrtp 时会在 CMake 里把 ENABLE_WEBRTC 关掉，此时 /index/api/webrtc 会 404。
        读取 CMakeCache.txt 并在关闭时打出明确提示（与是否传 -DENABLE_WEBRTC=ON 无关）。
        """
        cache = os.path.join(build_dir, "CMakeCache.txt")
        if not os.path.isfile(cache):
            return
        try:
            text = Path(cache).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return
        webrtc_on: bool | None = None
        openssl_on: bool | None = None
        for line in text.splitlines():
            if line.startswith("ENABLE_WEBRTC:"):
                webrtc_on = line.rstrip().upper().endswith("=ON")
            if line.startswith("ENABLE_OPENSSL:"):
                openssl_on = line.rstrip().upper().endswith("=ON")
        if webrtc_on is True:
            return
        if webrtc_on is None:
            return
        logger.error(
            "ZLMediaKit CMake 未开启 WebRTC（ENABLE_WEBRTC=OFF）。浏览器 POST /index/api/webrtc 将返回 404。 "
            "请在编译机安装 OpenSSL + libsrtp 开发包后删除构建目录 {} 再重新编译，例如："
            "Debian/Ubuntu: apt install -y libssl-dev libsrtp2-dev build-essential cmake；"
            "RHEL/Alma/Rocky: dnf install -y openssl-devel libsrtp-devel gcc-c++ cmake（无 libsrtp 包时需 EPEL 或源码编译安装）。",
            build_dir,
        )
        if openssl_on is False:
            logger.error("CMake 显示 ENABLE_OPENSSL=OFF（通常因未安装 openssl 开发包）。ZLMediaKit 会同步关闭 HTTPS/WSS/WebRTC。")

    def _should_build_from_source(self) -> bool:
        """
        是否允许进行“源码编译”：
        - 明确关闭：ZLM_BUILD_FROM_SOURCE=false
        - 资源不足：默认跳过并提示（可用 ZLM_BUILD_FORCE=true 强制）
        """
        build_from_source = settings.ZLM_BUILD_FROM_SOURCE
        zlm_build_env = os.getenv("ZLM_BUILD_FROM_SOURCE")
        if zlm_build_env is not None and str(zlm_build_env).strip().lower() in {"0", "false", "no", "off"}:
            build_from_source = False
        # 生产环境默认不在启动链路里源码编译（除非 .env/环境变量显式 ZLM_BUILD_FROM_SOURCE=true）
        # 注意：需在 config 里 load_dotenv，否则 .env 只进 settings、os.getenv 仍为 None。
        try:
            app_env = (settings.APP_ENV or "dev").lower()
            prod_explicit = zlm_build_env is not None and str(zlm_build_env).strip() != ""
            prod_opt_in = prod_explicit and str(zlm_build_env).strip().lower() in {"1", "true", "yes", "on"}
            if app_env in {"prod", "production"} and not prod_opt_in:
                if build_from_source:
                    logger.warning(
                        "Production env detected: skip ZLMediaKit build-from-source by default. "
                        "Set ZLM_BUILD_FROM_SOURCE=true in .env or the process environment to enable."
                    )
                build_from_source = False
        except Exception as e:
            logger.warning(f"Failed to check production environment: {e}")
        if not build_from_source:
            return False

        force = settings.ZLM_BUILD_FORCE
        if str(os.getenv("ZLM_BUILD_FORCE", "")).strip().lower() in {"1", "true", "yes"}:
            force = True
        if force:
            return True

        min_cpu = settings.ZLM_BUILD_MIN_CPU
        min_mem = settings.ZLM_BUILD_MIN_MEM_GB
        cpu, mem_gb = self._get_system_resources()
        if cpu < min_cpu or (mem_gb and mem_gb < min_mem):
            logger.warning(
                "Skip ZLMediaKit build from source due to low resources: cpu={} mem_gb={} (min_cpu={} min_mem_gb={}). "
                "Provide ZLM_FALLBACK_BINARY_URL or set ZLM_BUILD_FORCE=true to override.",
                cpu,
                mem_gb,
                min_cpu,
                min_mem,
            )
            return False
        return True

    def _extract_package(self, pkg: str, dest_dir: str, kind: str) -> None:
        os.makedirs(dest_dir, exist_ok=True)
        if kind == "zip":
            with zipfile.ZipFile(pkg, "r") as zip_ref:
                safe_extract_zip(zip_ref, dest_dir)
            return
        if kind == "tar.gz":
            with tarfile.open(pkg, "r:gz") as tar_ref:
                safe_extract_tar(tar_ref, dest_dir)
            return
        raise RuntimeError(f"Unsupported package kind: {kind}")

    async def _ensure_zltoolkit(self, zlm_root: str) -> bool:
        """
        ZLMediaKit 源码 zip 通常不含 git submodules，会缺 3rdpart/ZLToolKit。
        这里支持从独立 zip 下载并解压到期望目录。
        """
        toolkit_dir = os.path.join(zlm_root, "3rdpart", "ZLToolKit")
        if os.path.isdir(toolkit_dir) and os.listdir(toolkit_dir):
            return True

        url = (
            (settings.ZLM_ZLTOOLKIT_ZIP_URL or "").strip()
            or str(os.getenv(ZLM_ZLTOOLKIT_ZIP_URL_ENV, "")).strip()
        )
        if not url:
            # FIX [2026-07-22 P1]: 未显式配置时默认从 Gitee/GitHub 镜像自动选最快，
            # 原实现直接报错要求用户手工配置 ZLM_ZLTOOLKIT_ZIP_URL，导致 zip 源码链路必失败。
            if self._mirror_auto_select_enabled():
                url = await self._pick_fastest_mirror_async(ZLM_ZLTOOLKIT_ZIP_MIRRORS)
            else:
                url = ZLM_ZLTOOLKIT_ZIP_MIRRORS[1]
        if not url:
            logger.error(
                "ZLToolKit submodule is missing (expected at {}) and no download URL available. "
                "Please provide ZLM_ZLTOOLKIT_ZIP_URL (a zip of ZLToolKit) and restart.",
                toolkit_dir,
            )
            return False

        tmp_dir = os.path.join(os.path.dirname(zlm_root), "_tmp_submodules")
        os.makedirs(tmp_dir, exist_ok=True)
        pkg = os.path.join(tmp_dir, "zltoolkit.zip")
        try:
            logger.info(f"Downloading ZLToolKit submodule zip: {url}")
            await self._download_package(url, pkg)
            logger.info(f"Extracting ZLToolKit to {os.path.join(zlm_root, '3rdpart')}")
            # 先解压到临时目录，再把实际目录移动到 3rdpart/ZLToolKit
            extract_root = os.path.join(tmp_dir, "zltoolkit_extracted")
            if os.path.exists(extract_root):
                shutil.rmtree(extract_root, ignore_errors=True)
            os.makedirs(extract_root, exist_ok=True)
            self._extract_package(pkg, extract_root, "zip")

            # 寻找解压后的根目录（常见：ZLToolKit-master/）
            inner = None
            for name in os.listdir(extract_root):
                p = os.path.join(extract_root, name)
                if os.path.isdir(p) and "zltoolkit" in name.lower():
                    inner = p
                    break
            if not inner:
                # 兜底：如果直接解压出来就是源码文件
                inner = extract_root

            os.makedirs(os.path.join(zlm_root, "3rdpart"), exist_ok=True)
            if os.path.exists(toolkit_dir):
                shutil.rmtree(toolkit_dir, ignore_errors=True)
            shutil.move(inner, toolkit_dir)
            ok = os.path.isdir(toolkit_dir) and bool(os.listdir(toolkit_dir))
            if ok:
                logger.info("ZLToolKit submodule prepared successfully.")
            else:
                logger.error("ZLToolKit submodule still missing after extraction.")
            return ok
        except Exception as e:
            logger.error(f"Failed to prepare ZLToolKit submodule: {e}")
            return False
        finally:
            try:
                if os.path.exists(pkg):
                    os.remove(pkg)
            except Exception as e:
                logger.warning(f"Failed to remove ZLM package file: {e}")

    def _probe_url_latency(self, url: str, timeout: float = 5.0) -> float | None:
        """测量 URL 首字节延迟（秒），不可达/错误返回 None。仅用于镜像选路，不下载完整内容。"""
        import requests

        try:
            if url.endswith(".git"):
                # git 仓库探测 smart-http info/refs 端点
                probe_url = f"{url}/info/refs?service=git-upload-pack"
                headers = {}
            else:
                # zip 等文件用 Range 头只取首字节
                probe_url = url
                headers = {"Range": "bytes=0-0"}
            start_ts = time.time()
            with requests.get(probe_url, headers=headers, stream=True, timeout=(timeout, timeout)) as r:
                if r.status_code >= 400:
                    return None
                for _ in r.iter_content(chunk_size=1024):
                    break
            return time.time() - start_ts
        except Exception:
            return None

    def _pick_fastest_mirror(self, urls: list[str], timeout: float = 5.0) -> str:
        """并发探测多个镜像的首字节延迟，返回最快的可达镜像；全部不可达时返回第一个候选。"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        candidates = [u for u in dict.fromkeys(urls) if u]
        if not candidates:
            return ""
        if len(candidates) == 1:
            return candidates[0]

        results: dict[str, float] = {}
        with ThreadPoolExecutor(max_workers=len(candidates)) as pool:
            fut_map = {pool.submit(self._probe_url_latency, u, timeout): u for u in candidates}
            for fut in as_completed(fut_map):
                u = fut_map[fut]
                try:
                    lat = fut.result()
                except Exception:
                    lat = None
                if lat is not None:
                    results[u] = lat

        if not results:
            logger.warning(
                "All ZLM mirrors unreachable during probe; using first candidate: {}", candidates[0]
            )
            return candidates[0]

        best_url, best_lat = min(results.items(), key=lambda kv: kv[1])
        logger.info(
            "ZLM mirror probe: {} -> fastest: {} ({:.2f}s)",
            {u: f"{lat:.2f}s" for u, lat in results.items()},
            best_url,
            best_lat,
        )
        return best_url

    async def _pick_fastest_mirror_async(self, urls: list[str]) -> str:
        """_pick_fastest_mirror 的异步包装（探测为阻塞 HTTP，放线程池执行）。"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._pick_fastest_mirror, urls
        )

    def _mirror_auto_select_enabled(self) -> bool:
        try:
            return bool(settings.ZLM_MIRROR_AUTO_SELECT)
        except Exception:
            return True

    async def _prepare_zlm_source(self, src_dir: str) -> str | None:
        """
        准备 ZLMediaKit 源码目录，返回源码根目录（含 CMakeLists.txt）。
        优先级：
        1) git clone（支持 submodules，推荐）
        2) zip 下载（可能缺 submodules，需要额外补齐）
        """
        git_url = (
            (settings.ZLM_GIT_URL or "").strip()
            or str(os.getenv(ZLM_GIT_URL_ENV, "")).strip()
        )
        if not git_url and self._mirror_auto_select_enabled():
            # 用户未显式指定 git 源：并发探测 Gitee/GitHub 镜像，选最快（国内通常 Gitee 更快）
            git_url = await self._pick_fastest_mirror_async(ZLM_GIT_URL_MIRRORS)
        git_ref = (
            (settings.ZLM_GIT_REF or "").strip()
            or str(os.getenv(ZLM_GIT_REF_ENV, "")).strip()
            or "master"
        )
        if git_url:
            repo_dir = os.path.join(src_dir, "ZLMediaKit-git")
            # FIX [2026-07-29 P0]: 如果源码已存在且完整（含 CMakeLists.txt），跳过 clone。
            # 后端重启循环中每次重新 clone 会导致 ZLM 永远无法完成部署。
            # git clone --depth 1 约需 18 秒，但后端可能在几秒内被重启，clone 永远完不成。
            if os.path.exists(os.path.join(repo_dir, "CMakeLists.txt")):
                logger.info(f"ZLM source already exists at {repo_dir}, skip git clone (reuse on restart).")
                return repo_dir
            # 源码不完整（可能上次 clone 中途被中断），清理后重试
            if os.path.exists(repo_dir):
                logger.warning(f"ZLM source incomplete at {repo_dir}, removing and re-cloning.")
                shutil.rmtree(repo_dir, ignore_errors=True)
            os.makedirs(src_dir, exist_ok=True)
            try:
                logger.info(f"Cloning ZLMediaKit from git: {git_url} (ref={git_ref})")
                env = os.environ.copy()
                env.setdefault("GIT_TERMINAL_PROMPT", "0")
                env.setdefault("GIT_ASKPASS", "true")
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._run_cmd_stream(
                        ["git", "clone", "--progress", "--depth", "1", "--branch", git_ref, "--recurse-submodules", git_url, repo_dir],
                        cwd=None,
                        env=env,
                        timeout=300,
                        prefix="git",
                    ),
                )
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self._run_cmd_stream(
                            ["git", "submodule", "update", "--init", "--recursive"],
                            cwd=repo_dir,
                            env=env,
                            timeout=300,
                            prefix="git",
                        ),
                    )
                except Exception as sub_e:
                    # FIX [2026-07-22 P1]: 从 Gitee 镜像 clone 时，.gitmodules 中子模块 URL
                    # 仍指向 GitHub，submodule update 可能失败。原实现直接丢弃整个 clone 回退
                    # zip；现保留 clone 结果，由后续 _ensure_zltoolkit 从最快镜像补齐 ZLToolKit。
                    logger.warning(
                        f"Git submodule update failed ({sub_e}); keeping cloned repo and "
                        "will fill ZLToolKit via mirror zip in _ensure_zltoolkit."
                    )
                return repo_dir
            except subprocess.CalledProcessError as e:
                logger.error(f"Git clone failed: {e}")
                logger.warning("Falling back to zip source download.")
            except Exception as e:
                logger.error(f"Git clone error: {e}")
                logger.warning("Falling back to zip source download.")

        # zip 下载
        pkg = os.path.join(src_dir, "zlm_master.zip")
        src_url = (
            (settings.ZLM_SOURCE_ZIP_URL or "").strip()
            or str(os.getenv(ZLM_SOURCE_ZIP_URL_ENV, "")).strip()
        )
        if not src_url:
            if self._mirror_auto_select_enabled():
                # 并发探测 Gitee/GitHub zip 镜像，选最快
                src_url = await self._pick_fastest_mirror_async(ZLM_SOURCE_ZIP_MIRRORS)
            else:
                src_url = ZLM_OFFICIAL_SOURCE_ZIP_URL
        logger.info(f"Downloading ZLMediaKit source: {src_url}")
        await self._download_package(src_url, pkg)
        logger.info(f"Extracting ZLMediaKit source to {src_dir}")
        self._extract_package(pkg, src_dir, "zip")
        try:
            if os.path.exists(pkg):
                os.remove(pkg)
        except Exception as e:
            logger.warning(f"Failed to remove file: {e}")

        inner = None
        try:
            for name in os.listdir(src_dir):
                p = os.path.join(src_dir, name)
                if os.path.isdir(p) and name.lower().startswith("zlmediakit"):
                    inner = p
                    break
        except Exception:
            inner = None
        return inner

    async def _deploy_zlm_from_source(self) -> bool:
        """
        官方版本：下载最新源码并尝试编译出 MediaServer（二进制输出位置因平台而异）。
        依赖：
        - Windows: 需要已安装 VS Build Tools + CMake，并能在 PATH 找到 cmake
        - Linux: 需要 cmake/g++/make 等工具链
        """
        src_dir, build_dir = self._get_source_dirs()
        system = platform.system()
        # 是否允许源码编译（含资源门槛判断）
        if not self._should_build_from_source():
            return False

        # 若已有二进制，直接认为成功
        if os.path.exists(self.zlm_path):
            return True

        # 准备源码（优先 git clone，其次 zip；便于内网/镜像站）
        try:
            # FIX [2026-07-29 P0]: 不删除已有源码目录 — 后端重启循环中每次重新 clone
            # 会导致 ZLM 永远无法完成部署。如果源码已存在且完整（含 CMakeLists.txt），
            # 直接复用。仅在源码不完整时才清理重下。
            os.makedirs(src_dir, exist_ok=True)
            inner = await self._prepare_zlm_source(src_dir)
        except Exception as e:
            logger.error(f"Failed to download/extract official ZLMediaKit source: {e}")
            return False
        if not inner:
            logger.error("Cannot locate extracted ZLMediaKit source folder.")
            return False

        # 确保关键子模块存在（zip 源码通常不含 submodules）
        try:
            ok = await self._ensure_zltoolkit(inner)
            if not ok:
                return False
        except Exception as e:
            # FIX [2026-07-19 P1]: 原 except 静默 return False，zltoolkit 准备失败无法诊断。
            logger.error(f"Failed to ensure ZLToolkit submodule: {e}")
            return False

        # 编译
        try:
            # FIX [2026-07-29 P0]: 不删除已有构建目录 — 如果 CMakeCache.txt 已存在，
            # 说明 cmake configure 已完成，可直接 make（增量编译），避免重启循环中
            # 每次都重新 configure（约 30-60 秒）导致编译永远完不成。
            os.makedirs(build_dir, exist_ok=True)
            cmake_cache_file = os.path.join(build_dir, "CMakeCache.txt")
            need_configure = not os.path.exists(cmake_cache_file)

            # 基于 cmake 的最小自动构建（失败则回退预编译包）
            cfg_jobs = settings.ZLM_BUILD_JOBS
            if cfg_jobs <= 0:
                jobs = self._estimate_build_jobs()
                logger.info(f"ZLMediaKit build jobs auto-estimated: {jobs}")
            else:
                jobs = max(1, min(cfg_jobs, 8))
                logger.info(f"ZLMediaKit build jobs configured: {jobs}")
            # 强制开启 WebRTC/RTC：否则可能出现 /index/api/webrtc 404（模块未编进二进制）
            # 允许用户通过环境变量追加额外 CMake 参数（例如禁用某些模块/指定 openssl 路径）。
            extra_cmake_args_raw = str(os.getenv("ZLM_CMAKE_ARGS", "") or "").strip()
            extra_cmake_args = [a for a in extra_cmake_args_raw.split(" ") if a] if extra_cmake_args_raw else []

            base_flags = ["-DENABLE_WEBRTC=ON", "-DENABLE_RTC=ON"]
            if system == "Windows":
                cmake_config = ["cmake", "-S", inner, "-B", build_dir, "-A", "x64", *base_flags, *extra_cmake_args]
                cmake_build = ["cmake", "--build", build_dir, "--config", "Release", "--parallel", str(jobs)]
            else:
                cmake_config = ["cmake", "-S", inner, "-B", build_dir, "-DCMAKE_BUILD_TYPE=Release", *base_flags, *extra_cmake_args]
                cmake_build = ["cmake", "--build", build_dir, "--config", "Release", "--parallel", str(jobs)]

            if need_configure:
                logger.info("Configuring ZLMediaKit with CMake...")
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._run_cmd_stream(cmake_config, cwd=build_dir, env=None, timeout=600, prefix="cmake"),
                )
                self._warn_if_zlm_webrtc_disabled_in_cache(build_dir)
            else:
                logger.info(f"CMake cache exists at {cmake_cache_file}, skip configure (incremental build on restart).")
            logger.info("Building ZLMediaKit with CMake...")
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._run_cmd_stream(cmake_build, cwd=build_dir, env=None, timeout=1200, prefix="build"),
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"ZLMediaKit build failed: {e}")
            return False
        except Exception as e:
            logger.error(f"ZLMediaKit build error: {e}")
            return False

        # 产物定位：递归找 MediaServer(.exe)，然后移动到约定路径
        try:
            bin_dir = os.path.dirname(self.zlm_path)
            os.makedirs(bin_dir, exist_ok=True)
            binary_name = "MediaServer.exe" if system == "Windows" else "MediaServer"
            found_path = None
            for root, _, files in os.walk(build_dir):
                if binary_name in files:
                    found_path = os.path.join(root, binary_name)
                    break
            if not found_path:
                # 有些构建会把产物放在源码树的 release/ 下
                for root, _, files in os.walk(inner):
                    if binary_name in files:
                        found_path = os.path.join(root, binary_name)
                        break
            if not found_path:
                logger.error("Build succeeded but MediaServer binary not found.")
                return False
            logger.info(f"Using built MediaServer: {found_path}")
            shutil.copy2(found_path, self.zlm_path)
            return os.path.exists(self.zlm_path)
        except Exception as e:
            logger.error(f"Failed to install built MediaServer: {e}")
            return False

    async def _deploy_zlm(self):
        """
        Download and deploy ZLMediaKit binary if not exists
        """
        if os.path.exists(self.zlm_path):
            logger.info(f"ZLM deploy strategy hit: existing binary at {self.zlm_path}")
            return True

        system = platform.system()
        if system != "Linux":
            logger.warning(
                f"Skip embedded ZLMediaKit deploy on {system} (open-source default: Linux only). "
                f"Current OS: {system} {platform.release()}. "
                f"Please manually download ZLMediaKit binary for {system} and place it at {self.zlm_path}, "
                f"or configure external MEDIA_NODES to use an existing ZLM instance."
            )
            return False

        # 1) 预编译包兜底：用户显式提供下载地址（生产推荐）
        url = (settings.ZLM_FALLBACK_BINARY_URL or "").strip() or str(os.getenv("ZLM_FALLBACK_BINARY_URL", "")).strip()
        if url:
            logger.info("ZLM deploy strategy hit: fallback binary url provided (download prebuilt).")
            ok = await self._deploy_zlm_from_fallback_url(url)
            if ok and os.path.exists(self.zlm_path):
                return True
            logger.warning("ZLM deploy fallback url failed; will try build-from-source if allowed.")
        else:
            logger.info("ZLM deploy strategy: no fallback binary url provided.")

        # 2) 最后：源码编译（需要显式允许且资源足够；prod 默认跳过）
        logger.info("ZLM deploy strategy: trying build-from-source (last resort).")
        built = await self._deploy_zlm_from_source()
        if built and os.path.exists(self.zlm_path):
            logger.info("ZLMediaKit deployed from source build successfully!")
            return True

        logger.error(
            "ZLM deploy failed: no existing binary at {}, fallback prebuilt not available/succeeded, "
            "and build-from-source not available/succeeded (prod skips build unless ZLM_BUILD_FROM_SOURCE=true). "
            "Fix: copy a Linux MediaServer binary to that path, set ZLM_FALLBACK_BINARY_URL to a prebuilt tarball, "
            "or set ZLM_BUILD_FROM_SOURCE=true (and optionally ZLM_BUILD_FORCE=true). "
            "Alternatively configure external MEDIA_NODES so the app does not rely on embedded ZLM.",
            self.zlm_path,
        )
        return False

    async def _deploy_zlm_from_fallback_url(self, url: str) -> bool:
        """从预编译包下载并部署 MediaServer（二进制）。"""
        bin_dir = os.path.dirname(self.zlm_path)
        os.makedirs(bin_dir, exist_ok=True)
        logger.info(f"ZLMediaKit binary not found at {self.zlm_path}")
        logger.info("Attempting to download fallback ZLMediaKit package...")

        is_zip = url.lower().endswith(".zip")
        temp_file = os.path.join(bin_dir, "zlm_download" + (".zip" if is_zip else ".tar.gz"))

        try:
            await self._download_package(url, temp_file)
            logger.info(f"Downloaded package to {temp_file}. Extracting...")

            if is_zip:
                with zipfile.ZipFile(temp_file, "r") as zip_ref:
                    try:
                        safe_extract_zip(zip_ref, bin_dir)
                    except UnsafeArchiveError as e:
                        raise RuntimeError(f"Unsafe ZLM zip archive: {e}")
            else:
                with tarfile.open(temp_file, "r:gz") as tar_ref:
                    try:
                        safe_extract_tar(tar_ref, bin_dir)
                    except UnsafeArchiveError as e:
                        raise RuntimeError(f"Unsafe ZLM tar archive: {e}")

            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                logger.warning(f"Failed to remove temp tar file: {e}")

            if not os.path.exists(self.zlm_path):
                for root, _, files in os.walk(bin_dir):
                    binary_name = "MediaServer"
                    if binary_name in files:
                        found_path = os.path.join(root, binary_name)
                        logger.info(f"Moving found binary from {found_path} to {self.zlm_path}")
                        shutil.move(found_path, self.zlm_path)
                        cfg_name = "config.ini"
                        if cfg_name in files:
                            shutil.move(os.path.join(root, cfg_name), os.path.join(bin_dir, cfg_name))
                        break

            if os.path.exists(self.zlm_path):
                logger.info("ZLMediaKit deployment successful!")
                return True
            logger.error("Failed to locate ZLMediaKit binary after extraction.")
            return False
        except Exception as e:
            logger.error(f"Fallback deploy error: {e}")
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                logger.warning(f"Failed to remove temp tar file: {e}")
            return False

        # 预编译包下载逻辑已收敛到 _deploy_zlm_from_fallback_url

    async def _generate_config(self, node: dict | None = None):
        """
        Generate config.ini for ZLMediaKit

        FIX [2026-07-19]: 改为 async 方法，因为调用 async _ensure_port_free。
        原实现通过 run_in_executor 在线程池中运行，但 _ensure_port_free 内的
        time.sleep 会阻塞线程池中的工作线程，影响其他 executor 任务。
        改为 async 后，事件循环在 asyncio.sleep 期间可处理其他协程。
        """
        config = configparser.ConfigParser()
        # 强制保留配置项的大小写（ZLM 的 rtc.tcpPort 等项区分大小写）
        config.optionxform = str

        # Load existing config if available to preserve custom settings
        if os.path.exists(self.config_path):
            config.read(self.config_path)

        # Ensure core sections exist
        if not config.has_section("http"):
            config.add_section("http")
        if not config.has_section("general"):
            config.add_section("general")
        if not config.has_section("rtsp"):
            config.add_section("rtsp")
        if not config.has_section("rtmp"):
            config.add_section("rtmp")
        if not config.has_section("rtp_proxy"):
            config.add_section("rtp_proxy")
        if not config.has_section("api"):
            config.add_section("api")
        if not config.has_section("hook"):
            config.add_section("hook")
        if not config.has_section("rtc"):
            config.add_section("rtc")
        if not config.has_section("record"):
            config.add_section("record")
        if not config.has_section("hls"):
            config.add_section("hls")
        if not config.has_section("protocol"):
            config.add_section("protocol")

        # Overwrite with node settings (路 B) or fallback to global settings
        http_port = int((node or {}).get("http_port") or settings.MEDIA_SERVER_HTTP_PORT)
        rtsp_port = int((node or {}).get("rtsp_port") or settings.MEDIA_SERVER_RTSP_PORT)
        rtmp_port = int((node or {}).get("rtmp_port") or settings.MEDIA_SERVER_RTMP_PORT)
        rtp_port = int((node or {}).get("rtp_proxy_port") or settings.MEDIA_SERVER_RTP_PROXY_PORT)
        port_range = (node or {}).get("rtp_port_range")
        if not port_range:
            env_range = str(settings.MEDIA_SERVER_RTP_PROXY_PORT_RANGE or "").strip()
            if "-" in env_range:
                try:
                    left, right = env_range.split("-", 1)
                    start = int(left.strip() or 0)
                    end = int(right.strip() or 0)
                    if start > 0 and end >= start:
                        port_range = f"{start}-{end}"
                except Exception:
                    port_range = None
        port_range = self._normalize_rtp_port_range(port_range, rtp_port)

        await self._ensure_port_free(http_port)
        await self._ensure_port_free(rtsp_port)
        await self._ensure_port_free(rtmp_port)

        config.set("http", "port", str(http_port))
        config.set("general", "streamNoneReaderDelayMS", str(settings.ZLM_STREAM_NONE_READER_DELAY_MS))
        config.set("general", "wait_track_ready_ms", str(settings.ZLM_WAIT_TRACK_READY_MS))
        config.set("general", "wait_add_track_ms", str(settings.ZLM_WAIT_ADD_TRACK_MS))
        config.set("general", "maxStreamWaitMS", str(settings.ZLM_MAX_STREAM_WAIT_MS))
        # 关闭 ZLM 自身的流鉴权，完全交由后端 hook 控制（避免 401 Unauthorized）
        config.set("general", "checkStreamAuthority", "0")
        config.set("rtsp", "port", str(rtsp_port))
        config.set("rtmp", "port", str(rtmp_port))
        config.set("rtp_proxy", "port", str(rtp_port))
        config.set("rtp_proxy", "port_range", str(port_range))
        record_file_second = int((node or {}).get("record_file_second") or settings.ZLM_RECORD_FILE_SECOND)
        record_sample_ms = int((node or {}).get("record_sample_ms") or settings.ZLM_RECORD_SAMPLE_MS)
        protocol_mp4_max_second = int((node or {}).get("protocol_mp4_max_second") or settings.ZLM_PROTOCOL_MP4_MAX_SECOND)
        config.set("record", "fileSecond", str(max(30, record_file_second)))
        config.set("record", "sampleMS", str(max(100, record_sample_ms)))
        config.set("protocol", "mp4_max_second", str(max(30, protocol_mp4_max_second)))

        hls_seg_dur = settings.ZLM_HLS_SEG_DUR_SECONDS
        hls_seg_num = settings.ZLM_HLS_SEG_NUM
        config.set("hls", "enable", "1")
        config.set("hls", "segDur", str(max(1, hls_seg_dur)))
        config.set("hls", "segNum", str(max(1, hls_seg_num)))
        config.set("hls", "filePath", "./www")
        for _old_hls_key in ("segDuration", "saveTsInfo"):
            try:
                config.remove_option("hls", _old_hls_key)
            except Exception as e:
                logger.warning(f"Failed to remove HLS config option {_old_hls_key}: {e}")

        config.set("rtp_proxy", "checkSource", "1")
        for _old_key in ("check_source",):
            try:
                config.remove_option("rtp_proxy", _old_key)
            except Exception as e:
                logger.warning(f"Failed to remove RTP proxy config option {_old_key}: {e}")

        # WebRTC/RTC: 默认不写 [rtc] 段，避免硬编码 8000/8001 造成误解；
        # 只有显式开启 ZLM_WRITE_RTC_SECTION=true 时才写入（并且端口需显式配置）。
        try:
            write_rtc = settings.ZLM_WRITE_RTC_SECTION
        except Exception:
            write_rtc = False
        if write_rtc:
            rtc_port = int((node or {}).get("rtc_port") or settings.MEDIA_SERVER_RTC_PORT)
            rtc_tcp_port = int((node or {}).get("rtc_tcp_port") or settings.MEDIA_SERVER_RTC_TCP_PORT)
            backend_port = settings.BACKEND_PUBLIC_PORT

            # FIX [2026-07-29 P0]: rtc_tcp_port=0 时 ZLM 二进制回退到编译默认值 8000，
            # 会与后端 HTTP 端口（BACKEND_PUBLIC_PORT=8000）冲突，导致 uvicorn 绑定失败、
            # 应用启动后立即退出。默认回退到 rtc_port（WebRTC UDP/TCP 可共用同一端口号）。
            if rtc_tcp_port == 0:
                rtc_tcp_port = rtc_port
                logger.info(
                    f"[RTC_FIX] MEDIA_SERVER_RTC_TCP_PORT=0, falling back to rtc_port={rtc_port} "
                    f"(ZLM binary default 8000 would conflict with backend port {backend_port})"
                )

            # FIX [2026-07-29 P0]: 端口冲突时自动修正，而非仅 log error。
            # 原代码只记录 ERROR 日志但继续写入冲突端口 → ZLM 抢占 8000 → uvicorn 启动失败 →
            # lifespan 被 CancelledError 中断 → ZLM 被 cleanup 杀掉 → "启动不起来"。
            _RTC_SAFE_FALLBACK = 8554
            if rtc_port > 0 and rtc_port == backend_port:
                logger.warning(
                    f"[RTC_FIX] RTC UDP port {rtc_port} conflicts with BACKEND_PUBLIC_PORT {backend_port}! "
                    f"Auto-correcting to {_RTC_SAFE_FALLBACK}. "
                    f"Please set MEDIA_SERVER_RTC_PORT to a different port in .env"
                )
                rtc_port = _RTC_SAFE_FALLBACK
            if rtc_tcp_port > 0 and rtc_tcp_port == backend_port:
                logger.warning(
                    f"[RTC_FIX] RTC TCP port {rtc_tcp_port} conflicts with BACKEND_PUBLIC_PORT {backend_port}! "
                    f"Auto-correcting to {_RTC_SAFE_FALLBACK}. "
                    f"Please set MEDIA_SERVER_RTC_TCP_PORT to a different port in .env"
                )
                rtc_tcp_port = _RTC_SAFE_FALLBACK

            # 始终显式写入 rtc.port 和 rtc.tcpPort，防止 ZLM 使用编译默认值 8000
            if rtc_port > 0:
                config.set("rtc", "port", str(rtc_port))
            if rtc_tcp_port > 0:
                config.set("rtc", "tcpPort", str(rtc_tcp_port))
                try:
                    config.remove_option("rtc", "tcpport")
                except Exception as e:
                    logger.warning(f"Failed to remove RTC tcpport option: {e}")
            extern_ip = str((node or {}).get("public_host") or settings.STREAM_PUBLIC_HOST or "").strip()
            if extern_ip:
                config.set("rtc", "externIP", extern_ip)
                try:
                    config.remove_option("rtc", "externip")
                except Exception as e:
                    logger.warning(f"Failed to remove RTC externip option: {e}")
        else:
            try:
                config.remove_option("rtc", "port")
                config.remove_option("rtc", "tcpport")
                config.remove_option("rtc", "tcpPort")
                config.remove_option("rtc", "externip")
                config.remove_option("rtc", "externIP")
            except Exception as e:
                logger.warning(f"Failed to remove RTC config options: {e}")

        # Optional TLS ports if ZLM supports them (best-effort)
        https_port = int((node or {}).get("https_port") or settings.MEDIA_SERVER_HTTPS_PORT or 0)
        rtsps_port = int((node or {}).get("rtsps_port") or settings.MEDIA_SERVER_RTSPS_PORT or 0)
        rtmps_port = int((node or {}).get("rtmps_port") or settings.MEDIA_SERVER_RTMPS_PORT or 0)
        if https_port > 0:
            if not self._is_tcp_port_free(https_port):
                logger.warning(
                    f"ZLM HTTPS port {https_port} is occupied (e.g. by nginx). "
                    f"Falling back to sslport=0 (HTTPS disabled) to avoid ZLM startup failure."
                )
                https_port = 0
            else:
                await self._ensure_port_free(https_port)
        if rtsps_port > 0:
            if not self._is_tcp_port_free(rtsps_port):
                logger.warning(
                    f"ZLM RTSPS port {rtsps_port} is occupied. "
                    f"Falling back to sslport=0 (RTSPS disabled) to avoid ZLM startup failure."
                )
                rtsps_port = 0
            else:
                await self._ensure_port_free(rtsps_port)
        if rtmps_port > 0:
            if not self._is_tcp_port_free(rtmps_port):
                logger.warning(
                    f"ZLM RTMPS port {rtmps_port} is occupied. "
                    f"Falling back to sslport=0 (RTMPS disabled) to avoid ZLM startup failure."
                )
                rtmps_port = 0
            else:
                await self._ensure_port_free(rtmps_port)
        # 注意：若以前生成过 sslport=443，而当前未配置 https_port，
        # 需要显式覆盖/关闭该项。仅 remove_option 在部分版本/默认值下仍可能回退到 443，
        # 因此这里用 sslport=0 来强制禁用 HTTPS 监听，避免 443 被占用导致启动失败。
        try:
            if https_port > 0:
                config.set("http", "sslport", str(https_port))
            else:
                config.set("http", "sslport", "0")
        except Exception as e:
            logger.warning(f"Failed to set SSL port config: {e}")
        try:
            if rtsps_port > 0:
                config.set("rtsp", "sslport", str(rtsps_port))
            else:
                config.set("rtsp", "sslport", "0")
        except Exception as e:
            logger.warning(f"Failed to set RTSP SSL port config: {e}")
        try:
            if rtmps_port > 0:
                config.set("rtmp", "sslport", str(rtmps_port))
            else:
                config.set("rtmp", "sslport", "0")
        except Exception as e:
            logger.warning(f"Failed to set RTMP SSL port config: {e}")

        # API Secret
        api_secret = (node or {}).get("secret") or settings.MEDIA_SERVER_SECRET
        config.set("api", "secret", str(api_secret))

        # FIX [2026-07-17 P1]: hook URL 中的 secret 必须 URL-encode，
        # 否则 secret 含 +/=//& 等特殊字符时会破坏 URL 解析。
        # FastAPI request.query_params.get() 会自动 URL-decode，校验侧无需改动。
        from urllib.parse import quote as _url_quote
        _api_secret_q = _url_quote(str(api_secret), safe="")
        webhook_base = self._resolve_webhook_base(node)
        config.set("hook", "enable", "1")
        config.set("hook", "timeoutSec", str(settings.ZLM_HOOK_TIMEOUT_SEC))
        config.set("hook", "stream_changed_schemas", "rtsp/rtmp/fmp4/ts/hls/hls.fmp4/flv")
        config.set("hook", "on_server_started", f"{webhook_base}/on_server_started?secret={_api_secret_q}")
        config.set("hook", "on_server_keepalive", f"{webhook_base}/on_server_keepalive?secret={_api_secret_q}")
        config.set("hook", "on_play", f"{webhook_base}/on_play?secret={_api_secret_q}")
        config.set("hook", "on_publish", f"{webhook_base}/on_publish?secret={_api_secret_q}")
        config.set("hook", "on_stream_changed", f"{webhook_base}/on_stream_changed?secret={_api_secret_q}")
        config.set("hook", "on_stream_none_reader", f"{webhook_base}/on_stream_none_reader?secret={_api_secret_q}")
        config.set("hook", "on_send_rtp_stopped", f"{webhook_base}/on_send_rtp_stopped?secret={_api_secret_q}")
        config.set("hook", "on_rtp_server_timeout", f"{webhook_base}/on_rtp_server_timeout?secret={_api_secret_q}")
        config.set("hook", "on_record_mp4", f"{webhook_base}/on_record_mp4?secret={_api_secret_q}")
        config.set("hook", "on_stream_not_found", f"{webhook_base}/on_stream_not_found?secret={_api_secret_q}")

        self._write_config_if_changed(config)
        self._preflight_check_webhook_url(webhook_base)

    def _write_config_if_changed(self, config: configparser.ConfigParser) -> bool:
        """
        仅当配置内容变化时才写入 config.ini，避免每次重启都触发文件变更/热重载。
        返回：是否发生写入。
        """
        buf = io.StringIO()
        config.write(buf)
        new_text = buf.getvalue()
        old_text = ""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r") as f:
                    old_text = f.read()
        except Exception:
            old_text = ""
        if old_text == new_text:
            logger.info(f"ZLMediaKit config unchanged: {self.config_path}")
            return False
        try:
            with open(self.config_path, "w") as f:
                f.write(new_text)
            logger.info(f"Updated ZLMediaKit config: {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to write ZLMediaKit config: {e}")
            return False

    @staticmethod
    def _preflight_check_webhook_url(url: str) -> None:
        # FIX [2026-07-29 P2]: 此检查在 ZLM 启动阶段执行，此时后端 HTTP 服务尚未开始监听，
        # 必然返回 Connection refused。将警告降级为 debug，避免误导用户认为配置有误。
        # ZLM 启动后后端开始监听，webhook 回调将正常工作。
        try:
            from urllib.request import Request as _Req
            req = _Req(url, method="HEAD")
            with urllib_request.urlopen(req, timeout=2) as resp:
                if resp.status < 500:
                    return
        except Exception as e:
            logger.debug(f"Webhook preflight check skipped (backend not yet serving): {e}")
            return
        logger.debug(f"ZLM webhook URL preflight OK: {url}")

    async def _sync_embedded_node_ports_in_db(self) -> None:
        desired_http = settings.MEDIA_SERVER_HTTP_PORT
        desired_rtsp = settings.MEDIA_SERVER_RTSP_PORT
        desired_rtmp = settings.MEDIA_SERVER_RTMP_PORT
        desired_rtp = settings.MEDIA_SERVER_RTP_PROXY_PORT
        desired_secret = str(settings.MEDIA_SERVER_SECRET or "").strip() or None

        if desired_http <= 0:
            return

        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(select(MediaNode).where(MediaNode.is_embedded.is_(True)).limit(1))
                node = res.scalars().first()
                if not node:
                    return
                if getattr(node, "auto_config_enabled", None) is False:
                    return
                changed = False
                if desired_http > 0 and int(getattr(node, "http_port", 0) or 0) != desired_http:
                    node.http_port = desired_http
                    changed = True
                if desired_rtsp > 0 and int(getattr(node, "rtsp_port", 0) or 0) != desired_rtsp:
                    node.rtsp_port = desired_rtsp
                    changed = True
                if desired_rtmp > 0 and int(getattr(node, "rtmp_port", 0) or 0) != desired_rtmp:
                    node.rtmp_port = desired_rtmp
                    changed = True
                if desired_rtp > 0 and int(getattr(node, "rtp_proxy_port", 0) or 0) != desired_rtp:
                    node.rtp_proxy_port = desired_rtp
                    changed = True
                if desired_secret:
                    # FIX [2026-07-17 P0]: 必须使用 decrypted_secret setter（自动加密），
                    # 禁止直接赋值 node.secret = desired_secret。
                    # 原问题：node.secret 列存储 AES-256-GCM 密文，直接赋明文会导致：
                    # 1) decrypted_secret getter 调用 decrypt_field(明文) 返回 None
                    # 2) 后续所有使用 decrypted_secret 的代码路径降级回退到 MEDIA_SERVER_SECRET
                    # 3) 启动期 phase_check_secret_consistency 校验失败（decrypted_secret 返回 None）
                    # 比较时也必须解密后再比，避免 "密文 != 明文" 永远为 True 导致每次启动都重写。
                    _current_plain_secret = (
                        getattr(node, "decrypted_secret", None) or ""
                    )
                    if _current_plain_secret != desired_secret:
                        node.decrypted_secret = desired_secret  # setter 自动加密
                        changed = True
                if self._effective_rtp_range:
                    eff_start, eff_end = self._effective_rtp_range
                    if int(getattr(node, "rtp_port_range_start", 0) or 0) != eff_start:
                        node.rtp_port_range_start = eff_start
                        changed = True
                    if int(getattr(node, "rtp_port_range_end", 0) or 0) != eff_end:
                        node.rtp_port_range_end = eff_end
                        changed = True
                if changed:
                    await session.commit()
        except Exception:
            return

    async def is_running(self):
        """
        Check if ZLMediaKit is running
        """
        if self.process and self.process.poll() is None:
            return True
        return False

    def embedded_deploy_known_failed(self) -> bool:
        """本会话已尝试过部署且二进制仍不存在时，避免 health 无意义重试。二进制补齐后自动恢复。"""
        if not self.zlm_path:
            return False
        if os.path.isfile(self.zlm_path):
            self._embed_zlm_deploy_exhausted = False
            return False
        return bool(self._embed_zlm_deploy_exhausted)

    async def _deploy_then_start(self):
        """后台任务：先部署 ZLM 二进制（下载/编译），成功后再次调用 start() 拉起进程。

        部署失败时置 _embed_zlm_deploy_exhausted，避免反复重试拖垮启动链路；
        异常仅记录日志（fire_and_forget 异常回调也会兜底）。
        """
        try:
            deployed = await self._deploy_zlm()
            if not deployed:
                self._embed_zlm_deploy_exhausted = True
                logger.error("Failed to ensure ZLMediaKit binary. MediaServer will not start.")
                return
            # 二进制就绪，重新进入 start()（此时走“二进制存在”分支继续拉起进程；
            # start() 内部会重新检查 _running，stop() 后不会误拉起）
            await self.start()
        except Exception as e:
            logger.error(f"Embedded ZLM background deploy/start failed: {e}")

    async def start(self):
        """
        Start ZLMediaKit process
        """
        # N-07 monitor重启前检查_running标志，防止与stop()竞态
        if not self._running:
            return
        if not settings.EMBEDDED_ZLM_ENABLED:
            logger.info("Embedded ZLMediaKit is disabled by config (EMBEDDED_ZLM_ENABLED=false). Skipping start.")
            return
        if settings.ZLM_PREFER_EXTERNAL_NODES:
            try:
                hit = await self._detect_external_media_nodes_configured()
                if bool(hit.get("has_external")):
                    reasons: list[str] = []
                    if bool(hit.get("db_media_nodes")):
                        reasons.append(
                            f"DB media_nodes(count={int(hit.get('db_media_nodes_count') or 0)}, active_media_node_id={hit.get('active_media_node_id')})"
                        )
                    if bool(hit.get("env_media_nodes")):
                        reasons.append("ENV MEDIA_NODES(non-empty)")
                    reason_text = " + ".join(reasons) if reasons else "unknown"
                    logger.info(
                        "ZLM start strategy hit: external media nodes configured ({reason}); skip embedded ZLM start.",
                        reason=reason_text,
                    )
                    return
            except Exception as e:
                logger.warning(f"Failed to detect external media nodes: {e}")
        # Ensure binary exists (Auto-deploy if needed)
        if self.zlm_path and os.path.isfile(self.zlm_path):
            self._embed_zlm_deploy_exhausted = False
        elif self._embed_zlm_deploy_exhausted:
            logger.debug(
                "Embedded ZLM: skip deploy retry; MediaServer still missing at {} (see earlier ERROR).",
                self.zlm_path or "(no path)",
            )
            return
        else:
            # FIX [2026-07-22 P0]: 二进制缺失时的部署（GitHub 源码下载 ~90MB / 预编译包下载 / 源码编译）
            # 在低速网络下可能持续数分钟甚至永远无法完成，原同步 await 会阻塞整个 lifespan 启动，
            # 导致平台 API/Web 长时间不可访问。改为后台 fire_and_forget 部署+启动，
            # start() 立即返回；部署成功后由后台任务再次调用 start() 完成拉起。
            # readiness 已豁免 zlm_down，ZLM 就绪前仅影响视频播放，不影响登录/信令。
            if self._deploy_start_task is None or self._deploy_start_task.done():
                self._deploy_start_task = fire_and_forget(
                    self._deploy_then_start(),
                    name="embedded_zlm_deploy_start",
                )
                logger.info(
                    "Embedded ZLM: MediaServer binary missing; deploy+start running in background task "
                    "(app startup is NOT blocked). Video playback unavailable until ZLM is ready."
                )
            return

        deployed = await self._deploy_zlm()
        if not deployed:
            self._embed_zlm_deploy_exhausted = True
            logger.error("Failed to ensure ZLMediaKit binary. MediaServer will not start.")
            return

        if not os.path.exists(self.zlm_path):
            logger.warning(f"ZLMediaKit binary not found at {self.zlm_path}. Skipping start.")
            return
        self._warn_if_ffmpeg_missing()

        node_cfg = None
        ssl_pem_for_zlm: str | None = None
        try:
            async with AsyncSessionLocal() as session:
                emb_res = await session.execute(select(MediaNode).where(MediaNode.is_embedded.is_(True)).limit(1))
                emb_node = emb_res.scalars().first()
                if emb_node:
                    raw_ssl = getattr(emb_node, "zlm_ssl_merged_pem", None)
                    if raw_ssl and str(raw_ssl).strip():
                        ssl_pem_for_zlm = str(raw_ssl).strip()

                active_id = await get_active_media_node_id(session)
                db_node = await get_db_media_node_by_id(session, active_id) if active_id else None
                if not db_node:
                    db_node = await select_best_db_node(session)
                # 仅当节点开启“自动配置媒体服务”时才用其字段覆盖内置 ZLM 配置
                if db_node and bool(getattr(db_node, "auto_config_enabled", False)):
                    rtp_range = None
                    if (
                        str(getattr(db_node, "rtp_port_mode", "single") or "single").lower() == "range"
                        and int(getattr(db_node, "rtp_port_range_start", 0) or 0) > 0
                        and int(getattr(db_node, "rtp_port_range_end", 0) or 0) > 0
                        and int(getattr(db_node, "rtp_port_range_end", 0) or 0) >= int(getattr(db_node, "rtp_port_range_start", 0) or 0)
                    ):
                        rtp_range = f"{int(db_node.rtp_port_range_start)}-{int(db_node.rtp_port_range_end)}"
                    # FIX [2026-07-17 P0]: 必须使用 decrypted_secret（明文）写入 ZLM config.ini，
                    # 禁止直接使用 db_node.secret（AES-256-GCM 密文）。
                    # 原问题：将密文写入 ZLM [api] secret 后，ZLM 以密文作为鉴权期望值，
                    # 而 PyGBSentry 调用 ZLM API 时传明文 MEDIA_SERVER_SECRET，导致全部 401；
                    # 同时 ZLM hook 回调 URL 中携带密文 ?secret=，PyGBSentry verify_zlm_secret
                    # 比对明文失败，所有 on_publish/on_play/on_stream_changed 回调被拒，流无法建立。
                    _plain_secret_for_cfg = (
                        getattr(db_node, "decrypted_secret", None)
                        or str(settings.MEDIA_SERVER_SECRET or "")
                    )
                    node_cfg = {
                        "ip": db_node.host,
                        "http_port": db_node.http_port,
                        "rtsp_port": db_node.rtsp_port,
                        "rtmp_port": db_node.rtmp_port,
                        "rtp_proxy_port": db_node.rtp_proxy_port,
                        "rtp_port_range": rtp_range,
                        "secret": _plain_secret_for_cfg,
                        "hook_base_url": db_node.hook_base_url,
                        "hook_ip": db_node.hook_ip,
                        "https_port": db_node.https_port,
                        "rtsps_port": db_node.rtsps_port,
                        "rtmps_port": db_node.rtmps_port,
                        "record_file_second": getattr(db_node, "record_file_second", 0),
                        "record_sample_ms": getattr(db_node, "record_sample_ms", 0),
                        "protocol_mp4_max_second": getattr(db_node, "protocol_mp4_max_second", 0),
                        "rtc_port": getattr(db_node, "rtc_port", 0) or settings.MEDIA_SERVER_RTC_PORT,
                        "rtc_tcp_port": getattr(db_node, "rtc_tcp_port", 0) or settings.MEDIA_SERVER_RTC_TCP_PORT,
                        # FIX: [2026-07-16] 标记为内置节点，确保 _resolve_webhook_base 使用 loopback URL
                        "is_embedded": bool(getattr(db_node, "is_embedded", True)),
                    }
        except Exception:
            node_cfg = None
            ssl_pem_for_zlm = None
        if not ssl_pem_for_zlm:
            try:
                pem_path = str(settings.ZLM_SSL_MERGED_PEM_PATH or "").strip()
                if pem_path and os.path.isfile(pem_path):
                    ssl_pem_for_zlm = Path(pem_path).read_text(encoding="utf-8", errors="ignore").strip()
            except Exception:
                ssl_pem_for_zlm = None

        # FIX [2026-07-19]: _generate_config 已改为 async 方法（_ensure_port_free 用 asyncio.sleep），
        # 不再需要 run_in_executor 包装，直接 await 即可。
        await self._generate_config(node_cfg)
        await self._sync_embedded_node_ports_in_db()

        # Ensure execution permission on Linux
        if platform.system() == "Linux":
            os.chmod(self.zlm_path, 0o755)

        try:
            cwd = os.path.dirname(self.zlm_path)
            cmd = [self.zlm_path, "-c", self.config_path]
            ssl_pem_path = os.path.join(cwd, "zlm_merged_ssl.pem")
            if not ssl_pem_for_zlm:
                try:
                    if os.path.isfile(ssl_pem_path):
                        os.remove(ssl_pem_path)
                except Exception as e:
                    logger.warning(f"Failed to remove old SSL PEM file: {e}")
            if ssl_pem_for_zlm:
                try:
                    with open(ssl_pem_path, "w", encoding="utf-8") as sf:
                        sf.write(ssl_pem_for_zlm)
                    try:
                        os.chmod(ssl_pem_path, 0o600)
                    except Exception as e:
                        logger.warning(f"Failed to set socket option: {e}")
                    cmd.extend(["-s", ssl_pem_path])
                    logger.info("ZLMediaKit SSL: loading merged PEM from embedded media node ( -s )")
                except Exception as e:
                    logger.error(f"Failed to write ZLM SSL PEM file: {e}")

            # Start process
            self.process = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                # On Windows, we might want to hide the window
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            self._running = True
            logger.info(f"ZLMediaKit started with PID {self.process.pid}")

            # 启动 stdout 读取线程，确保启动失败原因可见
            self._stdout_stop.clear()
            self._stdout_thread = threading.Thread(target=self._drain_stdout, name="zlm-stdout", daemon=True)
            self._stdout_thread.start()

            # FIX: [2026-07-16] 启动后等待 HTTP API 就绪（最多 10 秒），
            # 避免进程已启动但 HTTP 端口尚未监听时 "All connection attempts failed"
            api_ready = await self._wait_http_api_ready(timeout=10.0)
            if not api_ready:
                logger.error(
                    "ZLMediaKit HTTP API did not become ready within 10s after start. "
                    f"Check ZLM stdout logs above for startup errors (port conflict, missing libs, config issues). "
                    f"HTTP port={settings.MEDIA_SERVER_HTTP_PORT}, "
                    f"config={self.config_path}"
                )
            else:
                logger.info("ZLMediaKit HTTP API is ready.")

            # Start monitoring task
            # P0-16 [2026-07-17]: 使用 fire_and_forget 替代裸 create_task，带异常回调和任务名
            self._monitor_task = fire_and_forget(
                self._monitor(),
                name="zlm_media_monitor",
            )
            self._probe_task = fire_and_forget(
                self._probe_webrtc_after_start(),
                name="zlm_webrtc_probe",
            )

        except Exception as e:
            logger.error(f"Failed to start ZLMediaKit: {e}")

    async def _wait_http_api_ready(self, timeout: float = 10.0) -> bool:
        """FIX: [2026-07-16] 等待 ZLM HTTP API 就绪（轮询 getServerConfig）。

        ZLM 进程启动后 HTTP 端口可能需要 1-3 秒才开始监听。
        如果不等待就绪，后续 API 调用会 "All connection attempts failed"。
        """
        import httpx
        port = settings.MEDIA_SERVER_HTTP_PORT
        host = str(settings.MEDIA_SERVER_HOST or "127.0.0.1").strip() or "127.0.0.1"
        secret = str(settings.MEDIA_SERVER_SECRET or "").strip()
        url = f"http://{host}:{port}/index/api/getServerConfig"
        deadline = time.monotonic() + timeout
        last_err = ""
        while time.monotonic() < deadline:
            # 如果进程已退出，立即返回
            if self.process and self.process.poll() is not None:
                logger.error(f"ZLMediaKit process exited (code={self.process.poll()}) during API readiness check.")
                return False
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.post(url, data={"secret": secret})
                    if resp.status_code == 200:
                        return True
                    last_err = f"HTTP {resp.status_code}"
            except Exception as e:
                last_err = str(e)
            await asyncio.sleep(0.5)
        if last_err:
            logger.warning(f"ZLM HTTP API readiness check failed: {last_err}")
        return False

    async def _probe_webrtc_after_start(self) -> None:
        await asyncio.sleep(1.2)
        try:
            port = settings.MEDIA_SERVER_HTTP_PORT
            host = str(settings.MEDIA_SERVER_HOST or "").strip()  # I3 回退值不再硬编码127.0.0.1
            url = f"http://{host}:{port}/index/api/webrtc"
            # SDP o= line hardcoded 127.0.0.1 → use host from settings
            placeholder_sdp = (
                "v=0\r\n"
                f"o=- 0 0 IN IP4 {host}\r\n"
                "s=-\r\n"
                "t=0 0\r\n"
            )
            # P0-fix [2026-07-17]: 禁止通过 URL 查询参数传递 ZLM secret（项目硬约束）
            # 原 `params["secret"] = _webrtc_secret` + `urlencode(params)` 让 secret 出现在
            # 反向代理日志、urllib 调试日志中。ZLM /index/api/webrtc 接口要求 body 为 raw SDP，
            # 无法用 form 字段同时传 secret。探测本质是判断 WebRTC 模块是否启用，
            # 因此不传 secret：401 表示接口存在且 ZLM 启用鉴权（视为可用）。
            params = {"app": "live", "stream": "probe", "type": "play"}
            req = urllib_request.Request(
                url + "?" + urllib_parse.urlencode(params),
                data=placeholder_sdp.encode("utf-8"),
                headers={"Content-Type": "text/plain;charset=utf-8"},
                method="POST",
            )
            try:
                with urllib_request.urlopen(req, timeout=2) as resp:
                    code = int(getattr(resp, "status", 200) or 200)
            except urllib_request.HTTPError as e:
                code = int(getattr(e, "code", 0) or 0)
            # FIX [2026-07-17 P4-4]: 401 表示 secret 鉴权通过但 WebRTC 模块缺失，
            # 不应与 404 混淆。仅当返回 404 时判定 WebRTC 不可用。
            if code != 404:
                return
            logger.error(
                "Embedded ZLMediaKit WebRTC is not available (POST /index/api/webrtc => HTTP 404). "
                "This usually means the current MediaServer binary was built without WebRTC/RTC. "
                "Install deps (OpenSSL + libsrtp dev) and rebuild, or replace MediaServer with a WebRTC-enabled build."
            )
            if not settings.ZLM_REBUILD_IF_WEBRTC_MISSING:
                return
            if platform.system() != "Linux":
                return
            if bool(getattr(self, "_webrtc_rebuild_attempted", False)):
                return
            setattr(self, "_webrtc_rebuild_attempted", True)
            self._probe_task = None
            try:
                await self.stop()
            except Exception as e:
                logger.warning(f"Failed to stop media manager: {e}")
            try:
                if self.zlm_path and os.path.isfile(self.zlm_path):
                    os.remove(self.zlm_path)
            except Exception as e:
                logger.warning(f"Failed to remove ZLM binary: {e}")
            try:
                self._embed_zlm_deploy_exhausted = False
            except Exception as e:
                logger.warning(f"Failed to reset deploy exhausted flag: {e}")
            await self.start()
        except Exception:
            return

    def _drain_stdout(self):
        try:
            if not self.process or not self.process.stdout:
                return
            while not self._stdout_stop.is_set():
                line = self.process.stdout.readline()
                if not line:
                    break
                try:
                    txt = line.decode(errors="ignore").rstrip() if isinstance(line, (bytes, bytearray)) else str(line).rstrip()
                except Exception:
                    txt = str(line).rstrip()
                if txt:
                    logger.info(f"[ZLM] {txt}")
        except Exception:
            return

    async def stop(self):
        if self.process and self.process.poll() is None:
            logger.info("Stopping ZLMediaKit...")
            self.process.terminate()
            try:
                await asyncio.to_thread(self.process.wait, timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                await asyncio.to_thread(self.process.wait)
            logger.info("ZLMediaKit stopped")
        self._running = False
        try:
            self._stdout_stop.set()
        except Exception as e:
            logger.warning(f"Failed to stop stdout reader: {e}")
        if self._stdout_thread and self._stdout_thread.is_alive():
            self._stdout_thread.join(timeout=3)
        self.process = None
        for _task_attr in ("_monitor_task", "_probe_task"):
            t = getattr(self, _task_attr, None)
            if t and not t.done():
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await t
            setattr(self, _task_attr, None)

    async def _monitor(self):
        _MAX_RESTARTS = 5
        _RESTART_BASE_DELAY = 5
        _STABLE_SECONDS = 60
        _stable_start = time.monotonic()
        while self._running and self.process:
            if self.process.poll() is not None:
                code = self.process.poll()
                if self._restart_count >= _MAX_RESTARTS:
                    logger.error(f"ZLMediaKit process exited (code={code}) and max restarts ({_MAX_RESTARTS}) reached. Not restarting.")
                    self._running = False
                    return
                delay = min(_RESTART_BASE_DELAY * (2 ** self._restart_count), 120)
                self._restart_count += 1
                logger.warning(f"ZLMediaKit process exited unexpectedly (code={code}). Restarting in {delay}s (attempt {self._restart_count}/{_MAX_RESTARTS})...")
                try:
                    self._stdout_stop.set()
                except Exception as e:
                    logger.warning(f"Failed to set stdout stop event: {e}")
                await asyncio.sleep(delay)
                # N-07 monitor重启前检查_running标志，防止与stop()竞态
                if not self._running:
                    return
                try:
                    await self.start()
                except Exception as start_err:
                    logger.error(f"ZLMediaKit restart failed: {start_err}")
                if self._running and self.process and self.process.poll() is None:
                    _stable_start = time.monotonic()
                    continue
                return

            if self._restart_count > 0 and (time.monotonic() - _stable_start) > _STABLE_SECONDS:
                self._restart_count = 0
                _stable_start = time.monotonic()
                logger.info("ZLMediaKit running stably, restart counter reset")

            await asyncio.sleep(1)

# Singleton
media_manager = MediaManager()


def get_media_server_info() -> dict:
    """返回当前媒体服务器连接信息（同步）。

    供 network/diagnose 端点获取 ZLM 拓扑节点信息使用。
    优先从 MEDIA_NODES 配置获取第一个节点，回退到 settings 中的 MEDIA_SERVER_* 配置。

    FIX: [2026-07-13] network.py 导入此函数但 2ad636a 从未定义，导致 ImportError。
    返回 dict 包含 host/http_port/secret，与调用方 media_info.get('host'/'http_port') 匹配。
    """
    try:
        from app.core.media_nodes import get_media_nodes
        nodes = get_media_nodes()
        if nodes:
            n = nodes[0]
            return {
                "host": str(n.get("host", "") or "127.0.0.1"),
                "http_port": int(n.get("http_port", 0) or 8880),
                "secret": str(n.get("secret", "") or ""),
            }
    except Exception as e:
        logger.warning(f"get_media_server_info: get_media_nodes failed: {e}")

    return {
        "host": str(settings.MEDIA_SERVER_HOST or "127.0.0.1"),
        "http_port": settings.MEDIA_SERVER_HTTP_PORT,
        "secret": str(settings.MEDIA_SERVER_SECRET or ""),
    }
