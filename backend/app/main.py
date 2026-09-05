# -------------------------------------------------------------------------
# 🚀 Project: PyGBSentry
# ✍️ Author: suoten
# 📧 Email: suoten@163.com
# 📄 License: AGPL-3.0-or-later WITH Classpath-Exception
# -------------------------------------------------------------------------

from contextlib import asynccontextmanager
from loguru import logger
import asyncio
from app.core.async_utils import fire_and_forget  # P0-16: 安全的火-忘任务
import random
import sys
import os


def _watch_bg_task(coro, name: str) -> asyncio.Task:
    """创建带异常监控的长生命周期后台任务。

    P1-fix [2026-07-17]: 原代码 9 个长生命周期后台任务均用裸 asyncio.create_task 创建，
    无 add_done_callback。任务因未捕获异常崩溃后会静默死亡，系统功能静默降级且无日志。
    """
    task = asyncio.create_task(coro, name=name)
    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            logger.debug(f"Background task {name} cancelled.")
            return
        exc = t.exception()
        if exc:
            logger.error(
                f"Background task {name} crashed with exception: {exc!r}",
                exc_info=exc,
            )
    task.add_done_callback(_on_done)
    return task

# Suppress OpenCV and FFMPEG noise (e.g. connection refused during media server startup)
os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"
os.environ["OPENCV_LOG_LEVEL"] = "ERROR"

from app.core.timezone import apply_process_timezone
import shutil

apply_process_timezone()

def _safe_print(msg: str) -> None:
    """编码安全输出：若 sys.stdout 无法编码则替换非 ASCII 字符。"""
    try:
        print(msg)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, 'encoding', 'utf-8') or 'utf-8'
        print(msg.encode(encoding, errors='replace').decode(encoding))

if not shutil.which("ffmpeg"):
    _safe_print("\n" + "="*65)
    _safe_print("WARNING: FFmpeg not detected. Snapshots, AI inference and recording may be limited!")  # i18n
    _safe_print("SUGGEST: Install FFmpeg, e.g. `apt install ffmpeg` (Debian/Ubuntu).")  # i18n
    _safe_print("="*65 + "\n")

# uvloop setup — auto-detect based on database backend
# uvloop (C extension) causes segfaults with aiosqlite (greenlet-based).
# Enable only for non-SQLite backends (mysql, postgresql, etc.) on non-Windows.
if sys.platform != "win32":
    try:
        from pathlib import Path as _P
        from dotenv import load_dotenv as _ld
        _ld(_P(__file__).resolve().parent.parent / ".env", override=False)
        _db_type = os.environ.get("DATABASE_TYPE", "").lower()
        if _db_type and _db_type not in ("sqlite",):
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass  # uvloop is optional
else:
    # FIX: [2026-07-04] Windows 默认使用 ProactorEventLoop，其 UDP 实现存在已知问题
    # (datagram_received 延迟回调/高并发丢包)，导致 SIP UDP 传输不响应。
    # 强制使用 SelectorEventLoop 以获得可靠的 UDP 支持。
    # 副作用：asyncio.create_subprocess_exec 在 Windows 上不可用（仅影响 certbot
    # 等 Linux 专属功能，subprocess.run 同步调用不受影响）。 [全栈工程师]
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Configure Loguru
from app.core.config import settings as _settings_for_log
_log_format_env = getattr(_settings_for_log, "LOG_FORMAT", None) or os.environ.get("LOG_FORMAT", "text").lower()
if _log_format_env == "json":
    _log_format = '{"timestamp":"{time:YYYY-MM-DD HH:mm:ss.SSS}","level":"{level}","module":"{name}","function":"{function}","line":{line},"message":"{message}"}'
else:
    _log_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
_log_dir = getattr(_settings_for_log, "LOG_DIR", None) or "logs"
logger.remove()
# FIX: [2026-07-16 P0-D] 接入日志脱敏器，所有 sink 的日志消息在写入前经过 mask_log_filter
# 过滤，将 password=xxx / token=xxx / 身份证号 / 手机号 等敏感信息替换为 ****，
# 满足等保 2.0 三级对日志中敏感信息脱敏的要求。
from app.core.log_masker import mask_log_filter as _mask_log_filter
# P3-05: 生产环境日志级别动态化 — prod=WARNING, dev=INFO, debug=DEBUG
# 可通过 LOG_LEVEL_STDERR 环境变量覆盖默认值
_app_env_for_log = (getattr(_settings_for_log, "APP_ENV", "dev") or "dev").lower()
_log_level_stderr = getattr(_settings_for_log, "LOG_LEVEL_STDERR", None) or ""
if not _log_level_stderr:
    if _app_env_for_log in {"prod", "production"}:
        _log_level_stderr = "WARNING"
    elif _app_env_for_log in {"debug"}:
        _log_level_stderr = "DEBUG"
    else:
        _log_level_stderr = "INFO"
logger.add(sys.stderr, level=_log_level_stderr, format=_log_format, filter=_mask_log_filter, enqueue=True)
# 哈希链审计日志 Sink — 每条日志包含前一条的 SHA256 摘要，实现防篡改链式校验
import json as _json
import hashlib as _hashlib_mod
import threading as _threading

class HashChainSink:
    """Loguru Sink：将审计日志以 JSON 行格式写入文件，每条日志包含 prev_hash 和 hash 字段形成哈希链。"""

    def __init__(self, path: str, rotation: str = "50 MB", retention: str = "180 days", compression: str = "gz"):
        self._path = path
        self._rotation = rotation
        self._retention = retention
        self._compression = compression
        self._prev_hash: str = "0" * 64
        self._lock = _threading.Lock()
        # Try to recover prev_hash from existing file
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    if lines:
                        last = lines[-1].strip()
                        if last:
                            data = _json.loads(last)
                            self._prev_hash = data.get("hash", "0" * 64)
        except Exception as init_err:
            # P1-10: 恢复失败不阻断启动，但记录警告
            import logging as _logging
            _logging.getLogger(__name__).warning(f"HashChainSink prev_hash recovery failed, starting fresh: {init_err}")
        self._file = open(path, "a", encoding="utf-8")

    def write(self, message: str) -> None:
        record = message.record
        timestamp = record["time"].strftime("%Y-%m-%d %H:%M:%S.") + f"{record['time'].microsecond // 1000:03d}"
        level = record["level"].name
        module = record["name"]
        msg_text = record["message"]

        with self._lock:
            entry = {
                "timestamp": timestamp,
                "level": level,
                "module": module,
                "message": msg_text,
                "prev_hash": self._prev_hash,
            }
            entry_bytes = _json.dumps(entry, ensure_ascii=False).encode("utf-8")
            current_hash = _hashlib_mod.sha256(entry_bytes).hexdigest()
            entry["hash"] = current_hash
            self._prev_hash = current_hash

            line = _json.dumps(entry, ensure_ascii=False) + "\n"
            self._file.write(line)
            self._file.flush()

            # Rotation support: close current file and open new one when size exceeds limit
            try:
                self._check_rotation()
            except Exception as rot_ex:
                # P1-11: _check_rotation 内部已有错误处理，此处为兜底安全网
                import logging as _logging
                _logging.getLogger(__name__).warning(f"HashChainSink rotation outer guard: {rot_ex}")

    def _check_rotation(self) -> None:
        """Check if file needs rotation based on size limit."""
        try:
            size_str = str(self._rotation).strip().upper()
            if size_str.endswith("MB"):
                max_bytes = int(float(size_str[:-2]) * 1024 * 1024)
            elif size_str.endswith("GB"):
                max_bytes = int(float(size_str[:-2]) * 1024 * 1024 * 1024)
            elif size_str.endswith("KB"):
                max_bytes = int(float(size_str[:-2]) * 1024)
            else:
                return
            if os.path.exists(self._path) and os.path.getsize(self._path) > max_bytes:
                # P1-10: 使用 try/except 保证文件句柄完整性 — 轮转失败时在 except 块重新打开文件
                import datetime as _dt
                self._file.close()
                try:
                    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                    rotated_path = f"{self._path}.{ts}"
                    try:
                        os.rename(self._path, rotated_path)
                    except OSError as rename_err:
                        # Windows fallback: os.rename 在文件被其他进程锁定时会失败
                        # 使用 shutil.copy2 + os.remove 作为后备，确保日志轮转仍可完成
                        try:
                            shutil.copy2(self._path, rotated_path)
                            os.remove(self._path)
                        except Exception as copy_err:
                            import logging as _logging
                            _logging.getLogger(__name__).warning(
                                f"HashChainSink rotation rename failed: {rename_err}; "
                                f"copy2+remove fallback also failed: {copy_err}"
                            )
                            rotated_path = self._path  # 两种方式均失败，原文件保留
                    # Preserve hash chain continuity: write a chain-link entry
                    last_hash = self._prev_hash
                    self._file = open(self._path, "a", encoding="utf-8")
                    link_entry = {
                        "timestamp": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                        "level": "INFO",
                        "module": "audit",
                        "message": f"hash_chain_continuation_from={rotated_path}",
                        "prev_hash": last_hash,
                    }
                    link_bytes = _json.dumps(link_entry, ensure_ascii=False).encode("utf-8")
                    link_hash = _hashlib_mod.sha256(link_bytes).hexdigest()
                    link_entry["hash"] = link_hash
                    self._prev_hash = link_hash
                    self._file.write(_json.dumps(link_entry, ensure_ascii=False) + "\n")
                    self._file.flush()
                except Exception as rot_err:
                    # P1-10: 轮转失败后确保文件句柄可用
                    import logging as _logging
                    _logging.getLogger(__name__).error(f"HashChainSink rotation failed: {rot_err}")
                    if not getattr(self._file, 'closed', True):
                        try:
                            self._file.close()
                        except Exception as _close_err:
                            # FIX [2026-07-17 P3-2]: 描述性日志替代 "silently_swallowed_exception"
                            logger.warning(f"HashChainSink: failed to close stale file handle during rotation: {_close_err}")
                    self._file = open(self._path, "a", encoding="utf-8")
        except Exception as outer_err:
            # P1-10: 外层异常不再静默吞掉
            import logging as _logging
            _logging.getLogger(__name__).warning(f"HashChainSink _check_rotation error: {outer_err}")

    def stop(self) -> None:
        with self._lock:
            if self._file and not self._file.closed:
                self._file.close()

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception as _del_err:
            # FIX [2026-07-17 P3-2]: 描述性日志替代 "silently_swallowed_exception"
            logger.warning(f"HashChainSink.__del__: failed to stop sink: {_del_err}")

logger.add(f"{_log_dir}/app.log", rotation="50 MB", retention="180 days", compression="gz", level="INFO", format=_log_format, filter=_mask_log_filter, enqueue=True, encoding="utf-8")  # P2-fix: 显式指定 UTF-8 编码避免 Windows GBK 区域乱码；日志保留180天(等保2.0三级要求)，P0-D: 接入脱敏过滤器
# 日志防篡改 — 哈希链审计日志，每条日志包含前一条的SHA256摘要
_audit_sink = HashChainSink(f"{_log_dir}/audit.log")
logger.add(_audit_sink.write, level="WARNING", filter=lambda record: _mask_log_filter(record) and record["level"].no >= 30, enqueue=True)

# 让标准 logging 模块的 INFO 日志（如 handlers.py 中的 SIP TRACE）也输出到 loguru
import logging
class _LoguruLoggingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            if record.levelno >= logging.ERROR:
                logger.error(msg)
            elif record.levelno >= logging.WARNING:
                logger.warning(msg)
            elif record.levelno >= logging.INFO:
                logger.info(msg)
            else:
                logger.debug(msg)
        except Exception:
            self.handleError(record)

_root = logging.getLogger()
# SECURITY: root logger level based on environment — INFO in production, DEBUG in dev
_root.setLevel(logging.INFO if str(getattr(_settings_for_log, "APP_ENV", "dev") or "dev").lower() in ("prod", "production") else logging.DEBUG)
_root.handlers.clear()
_root.addHandler(_LoguruLoggingHandler())

from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import JSONResponse, ORJSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.api.v1.api import api_router
from app.api.common.channel import router as common_channel_router
from app.api.common.play_start import router as play_start_router
from app.sip.server import sip_server
from app.sip.handlers import init_handlers
from app.sip.commander import SipCommander
from app.sip.invite import SipInvite
from app.sip.ptz import SipPtz
from app.sip.record import SipRecord
from app.sip.talk import SipTalk
from app.sip.playback_control import PlaybackControl
from app.sip.device_control import DeviceControl
from app.sip.catalog import Catalog
from app.services.media_manager import media_manager
from app.services.platform_service import PlatformService
from app.services.vision_hub import VisionHub
from app.services.health_service import health_service
from app.services.schema_upgrade import ensure_business_schema
from app.core.config import settings as app_settings
from app.services.region_import_service import ensure_regions_seeded_from_sql
from app.services.channel_placement_migration import ensure_split_channel_region_parents
from app.services.region_directory_split_migration import ensure_split_region_directory_parents
from app.core.plugin_manager import plugin_manager, HOOK_ON_STARTUP, HOOK_ON_SHUTDOWN
from app.core.redis import init_redis, close_redis, start_redis_watchdog
from app.db.session import AsyncSessionLocal, engine
from app.core.media_nodes_db import ensure_embedded_media_node
from app.utils.firewall import ensure_firewall_ports
from app.services.config_center_service import config_center_service
from app.core.ratelimit import init_rate_limiter
from sqlalchemy import text, inspect as sa_inspect
import app as app_pkg
import app.sip.commander
import app.sip.invite
import app.sip.ptz
import app.sip.record
import app.sip.talk
import app.sip.playback_control
import app.sip.device_control
import app.sip.catalog
import app.services.platform_service
import app.services.vision_hub
import app.services.notify_manager


async def _session_call(fn):
    """
    在 AsyncSession 内执行 async fn(db)。
    wait_for 必须包住「获取连接」整段，否则卡在 sqlite 等锁时超时不会触发。
    PRAGMA busy_timeout 已由 session.py 的 connect 事件处理器统一设置（每次新建连接自动执行），无需在此重复。
    """
    async with AsyncSessionLocal() as db:
        return await fn(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager — handles startup and shutdown.

    **Startup sequence** (in order):
    1. Database connectivity pre-check (configurable via ``DB_STARTUP_REQUIRED``)
    2. Schema migration via ``ensure_business_schema()``
    3. Settings cache warm-up and validation
    4. Redis connection pool initialization
    5. SIP server start (UDP/TCP/TLS transports)
    6. Plugin manager initialization and plugin loading
    7. Media node health probes and ZLMediaKit configuration sync
    8. Background task scheduling (health checks, watchdog, catalog sync)
    9. SSL/TLS certificate auto-renewal setup (if enabled)

    **Shutdown sequence** (reverse order):
    1. Cancel all background tasks and watchdogs
    2. Stop SIP server transports
    3. Close media node connections
    4. Flush plugin state and persist caches
    5. Close database and Redis connection pools

    Note: This function is long (~790 lines) because it orchestrates the
    entire application lifecycle. Each step is clearly commented.

    **Critical vs non-critical steps** (FIX: [2026-07-10] [全栈工程师]):
    - CRITICAL (fail-fast on failure, abort startup): DB pre-check, schema
      migration, init_db (admin/billing/media node), init_handlers, sip_server.start
    - NON-CRITICAL (log warning + continue): alarm_escalation_schema, plugin
      config load, plugin load, HOOK_ON_STARTUP, plugin health check

    Critical steps use ``raise`` to abort startup when they fail, so problems
    surface immediately instead of causing "started but unusable" silent failures.
    Non-critical steps degrade gracefully (feature unavailable but core works).
    """
    # FIX: [2026-07-17 P1] 在函数顶部初始化所有后台任务引用为 None，
    # 防止启动异常路径下 shutdown 时 NameError 掩盖原始异常
    _bg_dialog_cleanup = None
    _bg_ssrc_cleanup = None
    _bg_catalog_monitor = None
    _talk_cleanup_task = None
    paid_license_sync_task = None
    oss_heartbeat_task = None
    _log_drain_task = None

    # Startup
    logger.info(f"Using Database Dialect: {engine.dialect.name}")

    # FIX [2026-07-29 P0]: 检测多 worker 模式 — SIP 服务器不能多 worker 共享 UDP/TCP 端口
    # uvicorn --workers 2 时第二个 worker 绑定 SIP 端口失败→崩溃→supervisor 关闭所有 worker→应用 11ms 内死亡
    try:
        import multiprocessing as _mp
        _proc_name = _mp.current_process().name
        if _proc_name not in ("MainProcess", "SpawnProcess-1"):
            logger.warning(f"[WORKER_WARN] Process name={_proc_name} — if using uvicorn --workers N>1, SIP port binding will fail and cause immediate shutdown. Use --workers 1.")
    except Exception as _proc_err:
        logger.debug(f"[WORKER_WARN] process name check error: {_proc_err}")

    # CRITICAL: 数据库连接预检查 — DB 不可用时根据 DB_STARTUP_REQUIRED 决定是否中止启动
    logger.info("Startup step: DB connectivity pre-check...")
    try:
        async with engine.connect() as _conn:
            await _conn.execute(text("SELECT 1"))
        logger.info("Startup step: DB connectivity pre-check passed.")
    except Exception as _db_conn_err:
        if bool(settings.DB_STARTUP_REQUIRED):
            logger.error(
                f"FATAL: DB connectivity check failed: {_db_conn_err}. "
                "DB_STARTUP_REQUIRED=true, aborting startup. "
                "Check DATABASE_TYPE/HOST/PORT/USER/PASSWORD in .env, "
                "or set DB_STARTUP_REQUIRED=false for dev environments without a running DB."
            )
            raise
        logger.warning(
            f"Startup step: DB connectivity check failed: {_db_conn_err}. "
            "DB_STARTUP_REQUIRED=false, continuing startup in degraded mode (DB-dependent features will be unavailable)."
        )

    # Schema migration: use Alembic if USE_ALEMBIC=true, otherwise legacy schema_upgrade
    use_alembic = getattr(app_settings, 'USE_ALEMBIC', False)
    if use_alembic:
        import subprocess
        _backend_dir = os.path.dirname(os.path.dirname(__file__))

        # FIXED-P0: 检测数据库是否已有表但无 alembic_version 记录
        # 当数据库由 ensure_business_schema 创建时，表已存在但 alembic 不知道，
        # 导致 alembic upgrade head 尝试 CREATE TABLE 失败
        # 解决方案：检测到已有表时先 stamp head，再 upgrade（此时为 no-op）
        _need_stamp = False
        try:
            async with engine.connect() as conn:
                _dialect_name = (getattr(engine.dialect, "name", None) or "").lower()
                if _dialect_name == "sqlite":
                    _av_result = await conn.execute(text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
                    ))
                    if not _av_result.first():
                        _bt_result = await conn.execute(text(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('sqlite_sequence', '_alembic_tmp')"
                        ))
                        if _bt_result.fetchall():
                            _need_stamp = True
                elif _dialect_name == "postgresql":
                    # 检查 alembic_version 表是否存在且是否有版本记录
                    _av_result = await conn.execute(text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='alembic_version')"
                    ))
                    _av_exists = _av_result.scalar()
                    if not _av_exists:
                        # 无 alembic_version 表，检查是否有其他业务表
                        _bt_result = await conn.execute(text(
                            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name NOT IN ('alembic_version', '_alembic_tmp'))"
                        ))
                        if _bt_result.scalar():
                            _need_stamp = True
                    else:
                        # alembic_version 表存在但可能为空（之前部分运行）
                        _ver_result = await conn.execute(text(
                            "SELECT EXISTS (SELECT 1 FROM alembic_version)"
                        ))
                        if not _ver_result.scalar():
                            # 有表但无版本记录，检查是否有业务表
                            _bt_result = await conn.execute(text(
                                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name NOT IN ('alembic_version', '_alembic_tmp'))"
                            ))
                            if _bt_result.scalar():
                                _need_stamp = True
                elif _dialect_name == "mysql":
                    _av_result = await conn.execute(text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='alembic_version')"
                    ))
                    if not _av_result.scalar():
                        _bt_result = await conn.execute(text(
                            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name NOT IN ('alembic_version'))"
                        ))
                        if _bt_result.scalar():
                            _need_stamp = True
        except Exception as _stamp_check_err:
            logger.warning(f"alembic stamp pre-check error: {_stamp_check_err}")

        if _need_stamp:
            # FIX: [2026-07-12] stamp 初始迁移而非 head [全栈工程师]
            # 旧代码 stamp head 会跳过所有列补充迁移，导致：
            # - a1b2c3d4e5f6 ~ l4e5f6a7b8c9d 共 13 个迁移全部跳过
            # - users 表缺 auth_provider/auth_domain/site_role 等列
            # - init_db 查询时 PostgreSQL 报 "column does not exist" 崩溃
            # 改为 stamp 初始迁移 4bbb649f0063，后续 upgrade head 会执行所有
            # 幂等迁移，安全地补齐缺失的列和索引
            logger.info(
                "Startup step: stamping alembic at initial migration 4bbb649f0063 "
                "(database has tables but no alembic_version)..."
            )
            try:
                _stamp_result = subprocess.run(
                    [sys.executable, "-m", "alembic", "stamp", "4bbb649f0063"],
                    cwd=_backend_dir,
                    capture_output=True, text=True, timeout=30,
                    # FIX [2026-07-17]: 显式指定 UTF-8 编码，避免 Windows GBK 区域
                    # subprocess _readerthread UnicodeDecodeError (startup.log 中
                    # 'gbk' codec can't decode byte 0x94)。Alembic 输出含中文日志，
                    # 默认 text=True 使用 locale 编码 (GBK)，导致输出捕获线程崩溃，
                    # 进而使 alembic upgrade head 的实际错误被静默吞掉。
                    encoding="utf-8", errors="replace",
                )
                if _stamp_result.returncode == 0:
                    logger.info("Startup step: alembic stamp 4bbb649f0063 done.")
                else:
                    logger.warning(f"alembic stamp 4bbb649f0063 failed: {_stamp_result.stderr[-300:]}")
            except Exception as _stamp_err:
                logger.warning(f"alembic stamp 4bbb649f0063 error: {_stamp_err}")

        logger.info("Startup step: alembic upgrade head...")
        # FIXED-P0: 使用 subprocess 调用 alembic CLI，而非 import alembic.env
        # alembic/env.py 中 `from alembic import context` 引用第三方库，
        # 本地 alembic/ 目录会导致命名冲突，无论用 import 还是 importlib 都无法避免
        try:
            _result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=_backend_dir,
                capture_output=True, text=True, timeout=300,
                # FIX [2026-07-17]: 显式指定 UTF-8 编码，避免 Windows GBK 区域
                # subprocess _readerthread UnicodeDecodeError。原代码 text=True 使用
                # locale 默认编码 (Windows 中文=GBK)，Alembic 输出含中文日志时
                # _readerthread 线程崩溃，subprocess.run 返回 returncode=0 但
                # stdout/stderr 被截断，实际迁移错误被静默吞掉，导致后续
                # init_db 查询报 'no such column: tenant_subscriptions.downgrade_history'。
                encoding="utf-8", errors="replace",
            )
            if _result.returncode == 0:
                logger.info("Startup step: alembic upgrade head done.")
            else:
                _stderr = _result.stderr or ""
                logger.error(
                    f"FATAL: alembic upgrade head failed (exit {_result.returncode}): {_stderr[-800:]}. "
                    "All migrations are idempotent (sa.inspect precheck). "
                    "If you see 'already exists' errors, a migration may be missing the precheck. "
                    "Run 'python -m alembic upgrade head' manually to diagnose."
                )
                # FIX: [2026-07-12] 不再 stamp head 掩盖迁移失败 [全栈工程师]
                # 旧代码在 "already exists" 错误时自动 stamp head，导致：
                # 1. 后续列补充迁移（f1a2b3c4d5e6 ~ l4e5f6a7b8c9d）被永久跳过
                # 2. init_db 查询 User 表时因缺列崩溃
                # 所有迁移已改为 sa.inspect() 预检幂等模式，"already exists" 不应再出现
                if bool(getattr(app_settings, "DB_STARTUP_REQUIRED", True)):
                    raise RuntimeError(f"alembic upgrade head failed: {_stderr[-300:]}")
        except subprocess.TimeoutExpired:
            logger.error("FATAL: alembic upgrade head timed out (300s). Check for long-running data migrations.")
            if bool(getattr(app_settings, "DB_STARTUP_REQUIRED", True)):
                raise
        except Exception as _alembic_err:
            logger.error(f"FATAL: alembic upgrade head error: {_alembic_err}")
            if bool(getattr(app_settings, "DB_STARTUP_REQUIRED", True)):
                raise

        # FIXED-P0: alembic stamp head 只标记版本号，不创建缺失的表
        # 当数据库由 ensure_business_schema 部分创建时，某些表（如 ip_blacklist）
        # 可能不在 ensure_business_schema 的 SQL 列表中但存在于 ORM 模型中
        # 用 Base.metadata.create_all 兜底补建所有缺失的表
        try:
            from app.db.model_registry import ensure_model_registry_loaded
            from app.db.base import Base
            ensure_model_registry_loaded()
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Startup step: ensure all ORM tables exist (create_all fallback) done.")
        except Exception as _create_all_err:
            logger.warning(f"Startup step: create_all fallback error: {_create_all_err}")

        # FIX: [2026-07-12] 检测并修复 stamp head 污染的数据库 [全栈工程师]
        # 旧代码在迁移失败时自动 stamp head，导致 alembic_version=head 但实际缺列。
        # 此检查检测关键列是否缺失，若缺失则回退版本号到 k3c4d5e6f7g8 并重新
        # 执行 l4e5f6a7b8c9d 修复迁移（幂等，安全添加所有缺失列和索引）。
        try:
            async with engine.connect() as conn:
                def _check_critical_columns(sync_conn):
                    inspector = sa_inspect(sync_conn)
                    if not inspector.has_table('users'):
                        return False
                    existing = {c['name'] for c in inspector.get_columns('users')}
                    # auth_provider 由 f1a2b3c4d5e6 添加，是最可靠的 stamp head 污染指标
                    # 若 alembic_version=head 但 auth_provider 不存在，说明曾被 stamp head 污染
                    if 'auth_provider' not in existing:
                        return True
                    # FIX [2026-07-17]: 同时检查 tenant_subscriptions.downgrade_history
                    # 由 i1a2b3c4d5e6 添加，若缺失说明该迁移也未被正确执行
                    if inspector.has_table('tenant_subscriptions'):
                        ts_cols = {c['name'] for c in inspector.get_columns('tenant_subscriptions')}
                        if 'downgrade_history' not in ts_cols:
                            return True
                    return False
                _needs_repair = await conn.run_sync(_check_critical_columns)

            if _needs_repair:
                logger.warning(
                    "Startup step: detected stamp head pollution "
                    "(users.auth_provider missing but alembic_version=head). "
                    "Rolling back to k3c4d5e6f7g8 and re-running repair migration l4e5f6a7b8c9d..."
                )
                _stamp_repair = subprocess.run(
                    [sys.executable, "-m", "alembic", "stamp", "k3c4d5e6f7g8"],
                    cwd=_backend_dir,
                    capture_output=True, text=True, timeout=30,
                    # FIX [2026-07-17]: 同步修复 GBK 编码问题
                    encoding="utf-8", errors="replace",
                )
                if _stamp_repair.returncode == 0:
                    _repair_upgrade = subprocess.run(
                        [sys.executable, "-m", "alembic", "upgrade", "head"],
                        cwd=_backend_dir,
                        capture_output=True, text=True, timeout=300,
                        # FIX [2026-07-17]: 同步修复 GBK 编码问题
                        encoding="utf-8", errors="replace",
                    )
                    if _repair_upgrade.returncode == 0:
                        logger.info("Startup step: stamp head pollution repair done.")
                    else:
                        logger.error(
                            f"FATAL: repair upgrade failed: {_repair_upgrade.stderr[-500:]}"
                        )
                        if bool(getattr(app_settings, "DB_STARTUP_REQUIRED", True)):
                            raise RuntimeError(
                                f"Repair migration failed: {_repair_upgrade.stderr[-300:]}"
                            )
                else:
                    logger.error(f"FATAL: repair stamp failed: {_stamp_repair.stderr[-300:]}")
                    if bool(getattr(app_settings, "DB_STARTUP_REQUIRED", True)):
                        raise RuntimeError(f"Repair stamp failed: {_stamp_repair.stderr[-300:]}")
        except RuntimeError:
            raise
        except Exception as _repair_err:
            logger.warning(f"Startup step: schema repair check error: {_repair_err}")
    else:
        logger.info("Startup step: ensure_business_schema...")
        await ensure_business_schema()
        logger.info("Startup step: ensure_business_schema done.")
        # FIX: [验收] USE_ALEMBIC=false 时也执行 create_all 兜底，确保所有 ORM 表被创建。
        # ensure_business_schema 只创建业务表（SQL DDL），不覆盖所有 ORM 模型（53 张表）。
        # 新数据库（如删除重建后）需要 create_all 创建全部表，否则 assets/config_drafts 等
        # 表缺失，导致 /health、/config-center、/reports 等页面 500 错误。
        try:
            from app.db.model_registry import ensure_model_registry_loaded
            from app.db.base import Base
            ensure_model_registry_loaded()
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Startup step: ensure all ORM tables exist (create_all fallback) done.")
        except Exception as _create_all_err:
            logger.warning(f"Startup step: create_all fallback error: {_create_all_err}")

    logger.info("Startup step: ensure_alarm_escalation_schema...")
    try:
        from app.api.v1.endpoints.alarms import ensure_alarm_escalation_schema
        async with AsyncSessionLocal() as db:
            await asyncio.wait_for(ensure_alarm_escalation_schema(db), timeout=30)
        logger.info("Startup step: ensure_alarm_escalation_schema done.")
    except asyncio.TimeoutError:
        logger.warning("Startup step: ensure_alarm_escalation_schema timeout (30s), continue startup.")
    except Exception as e:
        logger.warning(f"Startup step: ensure_alarm_escalation_schema failed: {e}, continue startup.")

    # 初始化默认数据（admin 用户、计费方案等），支持 ADMIN_INITIAL_PASSWORD 重置密码
    # CRITICAL: init_db 创建 admin/billing/media node — 失败必须 fail-fast，否则"启动成功但无法登录"
    logger.info("Startup step: init_db (default admin user & billing)...")
    try:
        from app.initial_data import init_db
        await asyncio.wait_for(init_db(), timeout=30)
        logger.info("Startup step: init_db done.")
    except asyncio.TimeoutError:
        # FIX: [2026-07-10] 改为 fail-fast — init_db 超时意味着 admin/billing 未初始化 [全栈工程师]
        logger.error(
            "FATAL: init_db timeout (30s), aborting startup. "
            "Admin user and billing plans were not initialized. "
            "Check database connectivity or increase timeout."
        )
        raise
    except Exception as e:
        # FIX: [2026-07-10] 改为 fail-fast — 不再 continue startup 导致无法登录 [全栈工程师]
        logger.error(
            f"FATAL: init_db failed: {e}, aborting startup. "
            "Admin user and billing plans were not initialized.",
            exc_info=True,
        )
        raise

    # FIX: [2026-07-16] FIELD_ENCRYPTION_KEY 变更检测 —
    # 密钥非空但与加密数据不匹配时，所有 media_secret/sip_password 解密将静默失败，
    # 导致 SIP 认证失败、ZLM API 调用失败等隐蔽故障。启动时主动检测并发出显著警告。
    try:
        from app.db.session import AsyncSessionLocal as _SessionForCheck
        from app.models.media_node import MediaNode as _MediaNodeForCheck
        from app.core.field_crypto import decrypt_field as _decrypt_check
        from sqlalchemy import select as _select_check
        async with _SessionForCheck() as _sess:
            _row = (await _sess.execute(
                _select_check(_MediaNodeForCheck).where(_MediaNodeForCheck.is_embedded.is_(True)).limit(1)
            )).scalars().first()
            if _row and _row.secret:
                _dec = _decrypt_check(_row.secret, purpose="media_secret")
                if _dec is None:
                    _app_env = (settings.APP_ENV or "dev").lower()
                    _mismatch_msg = (
                        "========== FIELD_ENCRYPTION_KEY MISMATCH DETECTED ==========\n"
                        "The embedded media node's secret cannot be decrypted with the current FIELD_ENCRYPTION_KEY.\n"
                        "This means the key was changed after encrypted data was written.\n"
                        "Impact: ALL SIP password authentication and ZLM API calls will fail silently.\n"
                        "Fix: Restore the original FIELD_ENCRYPTION_KEY in your .env file.\n"
                        "     If the original key is lost, you must re-encrypt all passwords:\n"
                        "       1. Set a new FIELD_ENCRYPTION_KEY in .env\n"
                        "       2. Re-create or re-edit each device/platform to re-encrypt passwords\n"
                        "       3. Re-create the embedded media node via admin UI or scripts/ensure_embedded_media_node.py\n"
                        "============================================================"
                    )
                    # FIX [2026-07-17 P1-A1]: 生产环境必须 fail-fast 阻断启动，
                    # 避免出现"启动成功但所有设备无法注册"的静默故障。
                    # 违反 project_memory 硬约束第 19 条将导致 SIP 服务"假活"。
                    if _app_env in {"prod", "production"}:
                        logger.error(_mismatch_msg)
                        raise RuntimeError(_mismatch_msg)
                    logger.error(_mismatch_msg)
                else:
                    logger.info("Startup check: FIELD_ENCRYPTION_KEY verified (embedded node secret decrypts OK).")
    except Exception as _e:
        logger.warning(f"Startup check: FIELD_ENCRYPTION_KEY verification skipped: {_e}")

    # FIX: [2026-07-16] 启动时检查 ip_blacklist 中是否含有真实下级平台/设备 IP。
    # 背景：FIELD_ENCRYPTION_KEY 变更后，下级平台 REGISTER 因密码解密失败被拒 5 次，
    # 旧代码（未部署"解密失败不计入拉黑"逻辑时）会自动拉黑 IP。即使之后恢复密钥+部署新代码，
    # 该 IP 仍在黑名单中，所有 SIP 包在 server 层被直接丢弃，下级平台永远无法注册。
    # FIX: [2026-07-16 v2] 原 v1 只对比 parent_platforms.server_ip，但下级平台的实际信令 IP
    # 可能是 NAT 后的公网出口 IP，与配置的 server_ip 不同。现在也检查 Asset.ip_addr，
    # 并对所有非手动加入的黑名单条目（reason 不是 'manual'）输出警告。
    try:
        from app.db.session import AsyncSessionLocal as _SessionForBL
        from app.models.ip_blacklist import IpBlacklist as _IpBlacklistForCheck
        from app.models.platform import ParentPlatform as _ParentPlatformForCheck
        from app.models.asset import Asset as _AssetForCheck
        from sqlalchemy import select as _select_bl
        async with _SessionForBL() as _sess_bl:
            _bl_rows = (await _sess_bl.execute(_select_bl(_IpBlacklistForCheck))).scalars().all()
            if _bl_rows:
                _bl_ips = [r.ip for r in _bl_rows if r.ip]
                # 检查每个黑名单 IP 是否对应 ParentPlatform 表中的 server_ip
                _pf_rows = (await _sess_bl.execute(
                    _select_bl(_ParentPlatformForCheck.server_ip).distinct()
                )).scalars().all()
                _pf_ips = {ip for ip in _pf_rows if ip}
                # FIX v2: 也检查 Asset 表的 ip_addr（设备实际 IP）
                _asset_rows = (await _sess_bl.execute(
                    _select_bl(_AssetForCheck.ip_addr).distinct()
                )).scalars().all()
                _asset_ips = {ip for ip in _asset_rows if ip}
                # 合并所有已知合法 IP
                _known_ips = _pf_ips | _asset_ips
                _suspicious = [ip for ip in _bl_ips if ip in _known_ips]
                # FIX v2: 对所有非手动加入的黑名单条目也输出警告
                _auto_blacklisted = [r for r in _bl_rows if (r.reason or "").lower() not in ("manual", "manual_add")]
                # FIX: [2026-07-18] 启动时自动清除因 FIELD_ENCRYPTION_KEY 不匹配导致的误拉黑 IP。
                # 这些 IP 是系统自动添加的（非手动），通常是因为密码解密失败→认证失败→自动拉黑。
                # 即使恢复密钥后，这些 IP 仍在黑名单中，导致设备永远无法注册。
                # 手动添加的黑名单条目不受影响。
                _to_auto_clear = _auto_blacklisted
                if _to_auto_clear:
                    _clear_ips = [r.ip for r in _to_auto_clear if r.ip]
                    try:
                        from sqlalchemy import delete as _delete_bl
                        await _sess_bl.execute(
                            _delete_bl(_IpBlacklistForCheck).where(
                                _IpBlacklistForCheck.ip.in_(_clear_ips)
                            )
                        )
                        await _sess_bl.commit()
                        logger.warning(
                            "========== AUTO-CLEARED STALE BLACKLIST ENTRIES ==========\n"
                            f"Cleared {len(_clear_ips)} auto-blacklisted IPs (reason != manual):\n"
                            f"  {_clear_ips}\n"
                            "These IPs were likely auto-blacklisted due to FIELD_ENCRYPTION_KEY mismatch.\n"
                            "Manual blacklist entries are preserved. If an IP is a real threat,\n"
                            "add it manually via admin UI (安全中心→IP黑名单).\n"
                            "==========================================================="
                        )
                    except Exception as _clear_err:
                        logger.warning(f"Failed to auto-clear stale blacklist entries: {_clear_err}")
                elif _suspicious:
                    logger.error(
                        "========== POSSIBLE STALE BLACKLIST ENTRIES DETECTED ==========\n"
                        f"The following IPs are in ip_blacklist BUT also appear as server_ip/ip_addr in DB:\n"
                        f"  {_suspicious}\n"
                        "This typically happens when FIELD_ENCRYPTION_KEY was changed, causing platforms to fail\n"
                        "REGISTER auth 5 times and get auto-blacklisted. Even after restoring the key, these IPs\n"
                        "remain blocked and SIP packets are dropped at server level.\n"
                        "ACTION REQUIRED:\n"
                        "  1. Restore the original FIELD_ENCRYPTION_KEY in .env\n"
                        "  2. Remove these IPs from ip_blacklist via admin UI (安全中心→IP黑名单)\n"
                        "     or SQL: DELETE FROM ip_blacklist WHERE ip IN ("
                        + ",".join(f"'{ip}'" for ip in _suspicious) + ");\n"
                        "  3. Restart backend service\n"
                        "==============================================================="
                    )
                else:
                    logger.info(f"Startup check: ip_blacklist has {len(_bl_ips)} entries, all manual.")
    except Exception as _bl_err:
        logger.warning(f"Startup check: ip_blacklist verification skipped: {_bl_err}")

    # FIX [2026-07-18 P0]: 启动时检测 FIELD_ENCRYPTION_KEY 是否与数据库密文匹配。
    # 原问题：用户修改 FIELD_ENCRYPTION_KEY 后，所有 sip_password / media_secret 密文无法解密，
    # 导致 SIP 认证失败（设备被自动拉黑）和 ZLM API 鉴权失败。
    # 此检测在启动时执行一次解密探测，若失败则输出明确的修复指引。
    # FIX [2026-07-19]: 使用 allow_plaintext=False 严格模式——
    # 明文旧数据（加密功能启用前）也应被检测出来，提示用户运行迁移脚本加密。
    # 认证场景仍使用默认 allow_plaintext=True（明文兼容），不会受影响。
    try:
        from app.core.field_crypto import decrypt_field
        from app.models.platform import ParentPlatform as _PlatformForCheck
        from app.models.media_node import MediaNode as _MediaNodeForCheck
        from sqlalchemy import select as _select_dk
        _decrypt_fail_count = 0
        _decrypt_total_count = 0
        async with AsyncSessionLocal() as _sess_dk:
            # 探测平台密码字段（ParentPlatform.password）
            _plat_rows = (await _sess_dk.execute(
                _select_dk(_PlatformForCheck).where(_PlatformForCheck.password.isnot(None)).limit(5)
            )).scalars().all()
            for _p in _plat_rows:
                if not _p.password:
                    continue
                _decrypt_total_count += 1
                _decrypted = decrypt_field(_p.password, "sip_password", allow_plaintext=False)
                if _decrypted is None:
                    _decrypt_fail_count += 1
            # 探测媒体节点 secret 字段
            _mn_rows = (await _sess_dk.execute(
                _select_dk(_MediaNodeForCheck).where(_MediaNodeForCheck.secret.isnot(None)).limit(5)
            )).scalars().all()
            for _m in _mn_rows:
                if not _m.secret:
                    continue
                _decrypt_total_count += 1
                _decrypted = decrypt_field(_m.secret, "media_secret", allow_plaintext=False)
                if _decrypted is None:
                    _decrypt_fail_count += 1
        if _decrypt_fail_count > 0 and _decrypt_total_count > 0:
            logger.error(
                "========== FIELD_ENCRYPTION_KEY MISMATCH OR PLAINTEXT DATA DETECTED ==========\n"
                f"Decrypt probe: {_decrypt_fail_count}/{_decrypt_total_count} fields failed to decrypt.\n"
                "Possible causes:\n"
                "  1. FIELD_ENCRYPTION_KEY in .env does NOT match the key used to encrypt stored\n"
                "     passwords (密钥变更后的旧密文无法解密)\n"
                "  2. Some fields are still plaintext (加密功能启用前的旧数据未迁移)\n"
                "SIP device registration and ZLM API calls may fail.\n"
                "ACTION REQUIRED (choose one):\n"
                "  Option A (RECOMMENDED - if you have the original key):\n"
                "    1. Restore the original FIELD_ENCRYPTION_KEY in backend/.env\n"
                "    2. Restart backend service\n"
                "  Option B (if original key is lost - re-encrypt with new key):\n"
                "    1. Ensure FIELD_ENCRYPTION_KEY in .env is the new key\n"
                "    2. Run: cd backend && python scripts/reencrypt_fields.py\n"
                "    3. Restart backend service\n"
                "  Option C (if fields are plaintext - run migration to encrypt):\n"
                "    1. Ensure FIELD_ENCRYPTION_KEY in .env is set\n"
                "    2. Run: cd backend && alembic upgrade head\n"
                "    3. Restart backend service\n"
                "  After fix, auto-blacklisted IPs will be cleared on next startup.\n"
                "============================================================="
            )
        else:
            logger.info(f"Startup check: FIELD_ENCRYPTION_KEY decrypt probe OK ({_decrypt_total_count} fields).")
    except Exception as _dk_err:
        logger.warning(f"Startup check: FIELD_ENCRYPTION_KEY probe skipped: {_dk_err}")

    # 注入配置中心已发布的插件配置，供 load_plugins 时合并到各插件 config_template
    logger.info("Startup step: load_published_plugin_config...")
    try:
        async def _load_pub(db):
            return await config_center_service._load_published_modules(db)

        published = await asyncio.wait_for(_session_call(_load_pub), timeout=30)
        # _load_published_modules returns (revision, dict) tuple
        _revision, published_data = published
        plugin_manager._runtime_plugin_config = published_data.get("plugins") or {}
        logger.info("Startup step: load_published_plugin_config done.")
    except asyncio.TimeoutError:
        logger.warning("Startup step: load_published_plugin_config timeout (30s), using defaults")
        plugin_manager._runtime_plugin_config = {}
    except Exception as e:
        logger.warning("Load published plugin config failed: %s, using defaults" % e)
        plugin_manager._runtime_plugin_config = {}
    # Load Plugins
    logger.info("Startup step: plugin_manager.load_plugins...")
    try:
        plugin_manager.load_plugins()
        logger.info("Startup step: plugin_manager.load_plugins done.")
    except Exception as _plugins_err:
        # NON-CRITICAL: 插件加载失败记录 error 并继续启动（不影响核心 SIP/媒体服务）
        logger.error(f"Startup step: plugin_manager.load_plugins failed: {_plugins_err}, continue startup without plugins.")
    app_pkg.services.notify_manager.init_notify_manager()
    logger.info("Startup step: plugin_manager.emit(HOOK_ON_STARTUP)...")
    try:
        await asyncio.wait_for(plugin_manager.emit(HOOK_ON_STARTUP), timeout=20)
        logger.info("Startup step: plugin_manager.emit(HOOK_ON_STARTUP) done.")
    except asyncio.TimeoutError:
        logger.warning("Startup step: plugin_manager.emit(HOOK_ON_STARTUP) timeout (20s), continue startup.")
    except Exception as e:
        logger.warning(f"Startup step: plugin_manager.emit(HOOK_ON_STARTUP) failed: {e}, continue startup.")

    # G-08: 启动插件健康检查后台循环
    try:
        await plugin_manager.start_health_check_loop()
        logger.info("Startup step: plugin health check loop started.")
    except Exception as e:
        logger.warning(f"Startup step: plugin health check loop failed: {e}, continue startup.")

    # OSS 实例注册到 Server 端（仅在 PLUGIN_MARKETPLACE_ENABLED=True 时执行）
    if bool(settings.PLUGIN_MARKETPLACE_ENABLED):
        try:
            from app.services.license_service import _get_current_machine_code
            _machine_code = _get_current_machine_code()
            await plugin_manager.register_oss_instance(machine_code=_machine_code)
            logger.info("Startup step: OSS instance registered to marketplace server.")
        except Exception as e:
            logger.warning(f"Startup step: OSS instance register failed: {e}, continue startup.")

    # 续费即时推送：订阅 Redis license:refresh 频道（仅在 PLUGIN_MARKETPLACE_ENABLED=True 时启用）
    if bool(settings.PLUGIN_MARKETPLACE_ENABLED):
        try:
            # FIX: [2026-07-16 P1] 保存 task 引用到 plugin_manager，便于 shutdown 时优雅取消
            plugin_manager._license_refresh_task = _watch_bg_task(
                plugin_manager.start_license_refresh_subscriber(),
                "license_refresh_subscriber",
            )
            logger.info("Startup step: license refresh Redis subscriber started.")
        except Exception as e:
            logger.warning(f"Startup step: license refresh subscriber failed: {e}, continue startup.")
    else:
        logger.info("Startup step: PLUGIN_MARKETPLACE_ENABLED=False, marketplace integration disabled.")

    # 业务/行政区 parent 拆分迁移：默认不在启动时执行，避免 SQLite 锁等待拖死整站（与旧版「顺畅启动」一致）
    if not bool(settings.RUN_SPLIT_CATALOG_MIGRATIONS_ON_STARTUP):
        logger.info(
            "Startup step: split_migrations skipped (RUN_SPLIT_CATALOG_MIGRATIONS_ON_STARTUP=false). "
            "To migrate an old database, set to true in .env or run: python scripts/run_split_catalog_migrations.py"  # i18n
        )
    else:
        logger.info("Startup step: split_migrations...")
        _dialect = (getattr(engine.dialect, "name", None) or "").lower()
        try:
            resource_rows = 0

            async def _count_resources_rows() -> int:
                async with engine.connect() as conn:
                    if _dialect == "sqlite":
                        await conn.execute(text(f"PRAGMA busy_timeout={settings.SQLITE_BUSY_TIMEOUT_MS}"))
                    cnt_res = await conn.execute(text("SELECT COUNT(1) FROM resources"))
                    return int(cnt_res.scalar() or 0)

            logger.info("Startup step: split_migrations counting resources (raw connection)...")
            try:
                resource_rows = await asyncio.wait_for(_count_resources_rows(), timeout=25.0)
            except asyncio.TimeoutError:
                logger.error(
                    "Startup step: split_migrations COUNT timeout (25s). "
                    "Please check if another process is using pygbsentry.db (lsof ./pygbsentry.db), "
                    "or increase SQLITE_CONNECT_TIMEOUT_SECONDS in .env."  # i18n
                )
                resource_rows = -1
            except Exception as e:
                logger.warning(
                    "Startup step: split_migrations COUNT resources failed (skip migrations): {}",
                    e,
                )
                resource_rows = -1
            logger.info("Startup step: split_migrations count result: {}", resource_rows)

            if resource_rows == 0:
                logger.info(
                    "Startup step: split_migrations skipped (resources table empty, nothing to migrate)"
                )
            elif resource_rows < 0:
                logger.warning(
                    "Startup step: split_migrations skipped (could not count resources)"
                )
            else:
                logger.info(
                    "Startup step: split_migrations running (resources rows={})...",
                    resource_rows,
                )
                async with AsyncSessionLocal() as db:
                    logger.info("Startup step: ensure_split_channel_region_parents...")
                    n = await asyncio.wait_for(
                        ensure_split_channel_region_parents(db), timeout=60
                    )
                    if n:
                        logger.info("Startup step: channel placement split migration => {}", n)
                    logger.info("Startup step: ensure_split_channel_region_parents done.")
                    logger.info("Startup step: ensure_split_region_directory_parents...")
                    d = await asyncio.wait_for(
                        ensure_split_region_directory_parents(db), timeout=60
                    )
                    if d:
                        logger.info("Startup step: directory split migration => {}", d)
                    logger.info("Startup step: ensure_split_region_directory_parents done.")
            logger.info("Startup step: split_migrations done.")
        except asyncio.TimeoutError:
            logger.warning("Startup step: split_migrations timeout, continue startup.")
        except Exception as e:
            logger.warning("Channel placement split migration skipped/failed: {}", e)

    # 行政区划 SQL 体积大，旧实现每行 flush 会长时间阻塞启动；已改为批量 flush + 默认不在启动时导入
    if not bool(settings.RUN_REGION_SEED_ON_STARTUP):
        logger.info(
            "Startup step: ensure_regions_seeded_from_sql skipped (RUN_REGION_SEED_ON_STARTUP=false). "
            "To use built-in regions, set to true in .env or run: python scripts/seed_regions.py"  # i18n
        )
    else:
        logger.info("Startup step: ensure_regions_seeded_from_sql...")
        try:
            seeded = await asyncio.wait_for(_session_call(ensure_regions_seeded_from_sql), timeout=120)
            logger.info("Startup step: ensure_regions_seeded_from_sql => {}", seeded)
            logger.info("Startup step: ensure_regions_seeded_from_sql done.")
        except asyncio.TimeoutError:
            logger.warning("Startup step: ensure_regions_seeded_from_sql timeout (120s), continue startup.")
        except Exception as e:
            logger.warning(f"Startup step: ensure_regions_seeded_from_sql failed: {e}")

    # 内置 ZLM 节点记录：initial_data 已会创建；启动时再跑一遍在部分环境下会卡在 DB 会话，默认跳过
    if not bool(settings.ENSURE_EMBEDDED_MEDIA_NODE_ON_STARTUP):
        logger.info(
            "Startup step: ensure_embedded_media_node skipped (ENSURE_EMBEDDED_MEDIA_NODE_ON_STARTUP=false). "
            "If initial_data has not been run or node needs to be populated: python scripts/ensure_embedded_media_node.py"  # i18n
        )
    else:
        logger.info("Startup step: ensure_embedded_media_node...")
        try:
            embedded_id = await asyncio.wait_for(_session_call(ensure_embedded_media_node), timeout=30)
            if embedded_id:
                logger.info(f"Startup step: ensure_embedded_media_node ok (id={embedded_id}).")
            logger.info("Startup step: ensure_embedded_media_node done.")
        except asyncio.TimeoutError:
            logger.warning(
                "Startup step: ensure_embedded_media_node timeout (30s), continue startup. "
                "If this occurs frequently, check: lsof ./pygbsentry.db for multiple processes using the database"  # i18n
            )
        except Exception as e:
            logger.warning(f"Startup step: ensure_embedded_media_node failed: {e}")

    # SipStateBackend 初始化已移至 init_redis 之后，避免 Redis 未就绪时降级为 local
    # FIX [2026-07-13]: 原 get_sip_state_backend() 在 init_redis() 之前调用，
    # 导致 redis_client 为 None，SIP_STATE_BACKEND=redis 降级为 local

    # SECRET 一致性校验：对比 settings.MEDIA_SERVER_SECRET 与 DB 中 MediaNode.secret
    # P0-02: secret 列已加密存储，需通过 decrypted_secret 取明文后比较
    try:
        async def _check_secret_consistency(db):
            from app.models.media_node import MediaNode as _MN
            from sqlalchemy import select as _sel
            result = await db.execute(_sel(_MN).where(_MN.is_embedded).limit(1))
            return result.scalars().first()

        _secret_node = await asyncio.wait_for(_session_call(_check_secret_consistency), timeout=10)
        if _secret_node:
            _db_secret_plain = _secret_node.decrypted_secret
            if _db_secret_plain and _db_secret_plain != settings.MEDIA_SERVER_SECRET:
                _app_env = (settings.APP_ENV or "dev").lower()
                if _app_env in {"prod", "production"}:
                    logger.error(
                        "FATAL: MEDIA_SERVER_SECRET mismatch with DB MediaNode.secret (node_id=%s). "
                        "ZLM API calls will FAIL. Please ensure MEDIA_SERVER_SECRET in .env matches the secret in DB media_nodes table, "
                        "or run 'python scripts/update_media_node_secret.py' to sync DB with .env.",
                        _secret_node.id,
                    )
                    raise RuntimeError(
                        "MEDIA_SERVER_SECRET mismatch between .env and DB MediaNode.secret (node_id=%s). "
                        "ZLM API calls will fail. Please fix and restart." % _secret_node.id
                    )
                else:
                    logger.warning(
                        "MEDIA_SERVER_SECRET mismatch with DB MediaNode.secret (node_id=%s). "
                        "ZLM API calls may fail. This is acceptable in dev, but please ensure they match.",
                        _secret_node.id,
                    )
    except asyncio.TimeoutError:
        logger.warning("Startup step: secret consistency check timeout (10s), skipped.")
    except Exception as e:
        logger.warning(f"Startup step: secret consistency check skipped: {e}")

    # Print required ports and (optionally) auto-open firewall rules
    logger.info("Startup step: ensure_firewall_ports...")
    try:
        ensure_firewall_ports()
        logger.info("Startup step: ensure_firewall_ports done.")
    except Exception as e:
        logger.warning(f"Startup step: ensure_firewall_ports failed: {e}")

    if not settings.INIT_REDIS_ON_STARTUP:
        logger.info(
            "Startup step: init_redis skipped (INIT_REDIS_ON_STARTUP=false). "
            "Set INIT_REDIS_ON_STARTUP=true in .env and start redis-server when Redis is needed"  # i18n
        )
    else:
        logger.info("Startup step: init_redis...")
        try:
            redis_task = asyncio.create_task(init_redis())
            done, pending = await asyncio.wait({redis_task}, timeout=10)
            if redis_task in done:
                exc = redis_task.exception()
                if exc:
                    raise exc
                logger.info("Startup step: init_redis done.")
                start_redis_watchdog()
                # P2-21: 从 Redis 恢复自定义脱敏规则（失败不影响启动）
                try:
                    from app.core.log_masker import load_custom_rules_from_redis
                    loaded = await load_custom_rules_from_redis()
                    if loaded:
                        logger.info(f"Startup step: loaded {loaded} custom mask rules from Redis.")
                except Exception as _mask_load_err:
                    logger.warning(f"Startup step: load custom mask rules failed: {_mask_load_err}")
            else:
                for t in pending:
                    t.cancel()
                # CRITICAL: INIT_REDIS_ON_STARTUP=true 时 Redis 为关键服务，超时直接中止启动
                logger.error(
                    "FATAL: init_redis timeout (10s). "
                    "INIT_REDIS_ON_STARTUP=true, aborting startup. "
                    "Set INIT_REDIS_ON_STARTUP=false in .env if Redis is not required."
                )
                raise asyncio.TimeoutError("init_redis timeout (10s)")
        except Exception as e:
            # CRITICAL: INIT_REDIS_ON_STARTUP=true 时 Redis 为关键服务，初始化失败直接中止启动
            logger.error(
                f"FATAL: init_redis failed: {e}. "
                "INIT_REDIS_ON_STARTUP=true, aborting startup. "
                "Set INIT_REDIS_ON_STARTUP=false in .env if Redis is not required."
            )
            raise

    # SipStateBackend 主动初始化（必须在 init_redis 之后，确保 redis_client 已就绪）
    # FIX [2026-07-13]: 原位置在 init_redis 之前，导致 redis_client 为 None 降级为 local
    try:
        from app.sip.state_backend import get_sip_state_backend as _get_sip_state_backend
        _backend = _get_sip_state_backend()
        _backend_type = type(_backend).__name__
        logger.info(f"Startup step: SipStateBackend initialized (type={_backend_type})")
    except Exception as e:
        logger.warning(f"Startup step: SipStateBackend init failed: {e}, continue startup.")

    logger.info("Startup step: init_handlers...")
    try:
        init_handlers()
        logger.info("Startup step: init_handlers done.")
    except Exception as _handlers_err:
        # CRITICAL: SIP handlers 初始化失败将导致信令无法处理，中止启动
        logger.error(f"FATAL: init_handlers failed: {_handlers_err}, aborting startup.")
        raise

    # Init Commanders
    app_pkg.sip.commander.sip_commander = SipCommander(sip_server)
    app_pkg.sip.invite.sip_invite = SipInvite(sip_server)
    app_pkg.sip.ptz.sip_ptz = SipPtz(sip_server)
    app_pkg.sip.record.sip_record = SipRecord(sip_server)
    app_pkg.sip.talk.sip_talk = SipTalk(sip_server)
    app_pkg.sip.playback_control.playback_control = PlaybackControl(sip_server)
    app_pkg.sip.device_control.device_control = DeviceControl(sip_server)
    app_pkg.sip.catalog.catalog = Catalog(sip_server)

    logger.info("Startup step: sip_server.start...")
    try:
        await asyncio.wait_for(sip_server.start(), timeout=20)
        logger.info("Startup step: sip_server.start done.")
    except asyncio.TimeoutError:
        if settings.SIP_STARTUP_REQUIRED:
            logger.error("Startup step: sip_server.start timeout (20s), abort startup.")
            raise
        logger.warning("Startup step: sip_server.start timeout (20s), continue startup without SIP.")
    except OSError as e:
        if settings.SIP_STARTUP_REQUIRED:
            logger.error(f"Startup step: sip_server.start failed: {e}. abort startup.")
            raise
        logger.warning(f"Startup step: sip_server.start failed: {e}. Continue startup without SIP.")

    # FIX: [2026-07-10] RTP 超时配置校验 — 过短超时导致流在设备推流前被清理 [全栈工程师]
    _rtp_timeout = settings.RTP_SERVER_TIMEOUT_SECONDS
    if _rtp_timeout < 20:
        logger.warning(
            f"RTP_SERVER_TIMEOUT_SECONDS={_rtp_timeout} is too short for NAT environments. "
            "Recommend >= 30 for production. Streams may be dropped before devices start pushing."
        )

    # Start Platform Service (Cascade)
    app_pkg.services.platform_service.platform_service = PlatformService(sip_server)
    if not sip_server.running:
        logger.warning("Startup step: platform_service.start skipped (SIP not running).")
    else:
        logger.info("Startup step: platform_service.start...")
        try:
            await asyncio.wait_for(app_pkg.services.platform_service.platform_service.start(), timeout=20)
            logger.info("Startup step: platform_service.start done.")
        except asyncio.TimeoutError:
            logger.warning("Startup step: platform_service.start timeout (20s), continue startup.")

    # Start cluster Pub/Sub subscriber for RPC
    try:
        from app.core.redis import ha_cluster
        await ha_cluster.start_subscriber()
        logger.info("Startup step: cluster subscriber started.")
    except Exception as e:
        logger.warning(f"Startup step: cluster subscriber start failed (non-critical): {e}")

    logger.info("Startup step: platform_subscription_service.start...")
    try:
        from app.services.platform_subscription_service import platform_subscription_service
        await asyncio.wait_for(platform_subscription_service.start(), timeout=10)
        logger.info("Startup step: platform_subscription_service.start done.")
    except asyncio.TimeoutError:
        logger.warning("Startup step: platform_subscription_service.start timeout (10s), continue startup.")
    except Exception as e:
        logger.warning(f"Startup step: platform_subscription_service.start failed: {e}, continue startup.")

    logger.info("Startup step: device_subscription_service.start...")
    try:
        from app.services.device_subscription_service import device_subscription_service
        await asyncio.wait_for(device_subscription_service.start(), timeout=10)
        logger.info("Startup step: device_subscription_service.start done.")
    except asyncio.TimeoutError:
        logger.warning("Startup step: device_subscription_service.start timeout (10s), continue startup.")

    # start catalog aggregation periodic prune to prevent memory growth
    try:
        from app.sip.catalog import start_catalog_agg_prune
        start_catalog_agg_prune()
    except Exception as e:
        logger.warning(f"Startup step: catalog_agg_prune start failed (non-critical): {e}")

    # FIX R23-SEVERE: 周期性清理 catalog_runtime 内存缓存，避免 _RUNTIME_STATE 无限增长
    try:
        from app.sip.catalog_runtime import start_catalog_runtime_cleanup
        start_catalog_runtime_cleanup()
        logger.info("Startup step: catalog_runtime cleanup loop started.")
    except Exception as e:
        logger.warning(f"Startup step: catalog_runtime cleanup loop start failed (non-critical): {e}")

    # Start AI Vision Hub
    app_pkg.services.vision_hub.vision_hub = VisionHub()
    logger.info("Startup step: vision_hub.start...")
    try:
        await asyncio.wait_for(app_pkg.services.vision_hub.vision_hub.start(), timeout=20)
        logger.info("Startup step: vision_hub.start done.")
    except asyncio.TimeoutError:
        logger.warning("Startup step: vision_hub.start timeout (20s), continue startup.")

    # Start Embedded ZLMediaKit（首次源码编译可能极久，默认 EMBEDDED_ZLM_START_TIMEOUT_SECONDS=3600）
    zlm_boot_timeout = settings.EMBEDDED_ZLM_START_TIMEOUT_SECONDS
    logger.info("Startup step: media_manager.start (embedded ZLM)...")
    try:
        if zlm_boot_timeout > 0:
            await asyncio.wait_for(media_manager.start(), timeout=float(zlm_boot_timeout))
        else:
            await media_manager.start()
        logger.info("Startup step: media_manager.start done.")
    except asyncio.TimeoutError:
        logger.error(
            "Startup step: media_manager.start timeout ({}s), continue startup without embedded ZLM. "
            "If building ZLM from source, raise EMBEDDED_ZLM_START_TIMEOUT_SECONDS in .env or use a prebuilt MediaServer.",
            zlm_boot_timeout,
        )
    except Exception as e:
        logger.error(f"Startup step: media_manager.start failed: {e}")

    # Start Health Service
    logger.info("Startup step: health_service.start...")
    try:
        await asyncio.wait_for(health_service.start(), timeout=20)
        logger.info("Startup step: health_service.start done.")
    except asyncio.TimeoutError:
        logger.warning("Startup step: health_service.start timeout (20s), continue startup.")

    # Start default background tasks
    try:
        from app.services.tasks.task_manager import start_all_background_tasks
        await start_all_background_tasks(plugin_manager=plugin_manager)
    except Exception as _bg_tasks_err:
        # NON-CRITICAL: 后台任务启动失败记录 error 并继续启动
        logger.error(f"Startup step: start_all_background_tasks failed: {_bg_tasks_err}, continue startup.")

    # Start talk session cleanup loop
    _talk_cleanup_task = None
    try:
        from app.sip.talk import start_talk_cleanup_loop
        _talk_cleanup_task = _watch_bg_task(start_talk_cleanup_loop(), "talk_cleanup_loop")
        logger.info("Startup step: talk session cleanup loop started.")
    except Exception as e:
        logger.warning(f"Startup step: talk cleanup loop failed: {e}")

    # SSL certbot startup check
    try:
        from app.services.ssl_certbot.certbot_manager import on_startup
        await asyncio.wait_for(on_startup(), timeout=130)
    except asyncio.TimeoutError:
        logger.warning("SSL certbot startup check timeout (130s), continuing startup.")
    except Exception as e:
        logger.warning("SSL certbot startup check error (non-fatal): %s", e)

    # 启动日志 WebSocket 队列消费协程
    from app.api.v1.endpoints.logs import log_manager, _get_log_queue

    async def _drain_log_queue(manager, get_queue):
        while True:
            try:
                q = get_queue()
                log_entry = await asyncio.wait_for(q.get(), timeout=5.0)
                await manager.broadcast_log(log_entry)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                # FIX [2026-07-17 P1-E3]: 禁止静默吞异常，必须记录日志以便排查广播故障
                logger.warning(f"_drain_log_queue error: {e}")
                await asyncio.sleep(1)

    _log_drain_task = _watch_bg_task(_drain_log_queue(log_manager, _get_log_queue), "log_drain_queue")
    logger.info("Startup step: log queue drainer started.")

    # FIX [2026-07-17 P1-E7]: 注册 SIGHUP 信号处理器，支持配置热加载。
    # 收到 SIGHUP 时重新读取 .env 文件并刷新运行时配置（IP 黑名单等）。
    import signal as _signal
    from pathlib import Path as _Path
    from dotenv import load_dotenv as _load_dotenv

    def _on_sighup(*_args):
        """SIGHUP handler: reload .env and trigger runtime config refresh."""
        try:
            _env_path = _Path(__file__).resolve().parent.parent / ".env"
            if _env_path.exists():
                _load_dotenv(_env_path, override=True)
                logger.info("[SIGHUP] .env reloaded.")
            # P1-fix: 重新实例化 settings 单例，使 SIP_*/MEDIA_*/GB28181_* 等字段热生效
            # 原 SIGHUP 仅更新 os.environ，但 settings 是模块加载时一次性实例化的 Pydantic 单例
            try:
                from app.core import config as _config_mod
                _config_mod.settings = _config_mod.Settings()
                logger.info("[SIGHUP] settings singleton reloaded.")
                # 同步刷新 settings_cache 模块的缓存（避免旧值残留 30s TTL）
                try:
                    from app.core import settings_cache as _sc_mod
                    _sc_mod._cache.clear()
                    logger.info("[SIGHUP] settings_cache cleared.")
                except Exception as _sc_err:
                    logger.warning(f"[SIGHUP] settings_cache clear failed: {_sc_err}")
            except Exception as _settings_err:
                logger.error(f"[SIGHUP] settings reload failed: {_settings_err}")
            # 触发 IP 黑名单重载（非阻塞，使用 fire_and_forget）
            try:
                fire_and_forget(sip_server.reload_ip_blacklist())
                logger.info("[SIGHUP] IP blacklist reload triggered.")
            except Exception as _bl_err:
                logger.warning(f"[SIGHUP] IP blacklist reload failed: {_bl_err}")
            # 触发 TLS 证书热加载
            try:
                fire_and_forget(sip_server.reload_tls_cert())
                logger.info("[SIGHUP] TLS cert reload triggered.")
            except Exception as _tls_err:
                logger.warning(f"[SIGHUP] TLS cert reload failed: {_tls_err}")
        except Exception as e:
            logger.error(f"[SIGHUP] Hot reload failed: {e}")

    try:
        if sys.platform != "win32":
            asyncio.get_running_loop().add_signal_handler(_signal.SIGHUP, _on_sighup)
            logger.info("Startup step: SIGHUP hot-reload handler registered.")
    except (ValueError, RuntimeError, NotImplementedError) as _sig_err:
        logger.warning(f"Startup step: SIGHUP handler registration failed (non-critical): {_sig_err}")

    # FIX [2026-07-29 P0]: 注册 SIGTERM/SIGINT 信号处理器，记录是什么信号触发了 shutdown。
    # 根因诊断：应用启动后 11ms 即被 kill，需要知道信号来源（systemd/宝塔/Docker/OOM）。
    import traceback as _traceback_mod
    _shutdown_signal_received = {"signal": None}

    def _on_shutdown_signal(signum, *_args):
        _sig_name = _signal.Signals(signum).name if hasattr(_signal, 'Signals') else f"signal({signum})"
        _stack = ''.join(_traceback_mod.format_stack())
        logger.error(
            f"[SHUTDOWN_SIGNAL] Received {_sig_name} (pid={os.getpid()}) — "
            f"this is what triggered the shutdown. Stack trace:\n{_stack}"
        )
        _shutdown_signal_received["signal"] = _sig_name

    try:
        if sys.platform != "win32":
            asyncio.get_running_loop().add_signal_handler(_signal.SIGTERM, _on_shutdown_signal, _signal.SIGTERM)
            asyncio.get_running_loop().add_signal_handler(_signal.SIGINT, _on_shutdown_signal, _signal.SIGINT)
            logger.info("Startup step: SIGTERM/SIGINT diagnostic handlers registered.")
    except (ValueError, RuntimeError, NotImplementedError) as _sig_err:
        logger.warning(f"Startup step: SIGTERM/SIGINT handler registration failed (non-critical): {_sig_err}")

    logger.info("Startup complete.")

    _security_warnings = []
    if not settings.PLUGIN_LICENSE_MACHINE_CODE_ENABLED:
        _security_warnings.append("PLUGIN_LICENSE_MACHINE_CODE_ENABLED=False: machine code binding disabled, license can be copied across machines")  # i18n
    if not settings.PLUGIN_LICENSE_ACTIVATION_TOKEN_ENABLED:
        _security_warnings.append("PLUGIN_LICENSE_ACTIVATION_TOKEN_ENABLED=False: activation token disabled, trial period can be reset")  # i18n
    if not settings.PLUGIN_PACKAGE_INTEGRITY_REQUIRED_IN_PROD:
        _security_warnings.append("PLUGIN_PACKAGE_INTEGRITY_REQUIRED_IN_PROD=False: package signature verification disabled, plugin packages can be tampered")  # i18n
    if _security_warnings and (settings.APP_ENV or "dev").lower() in {"prod", "production"}:
        for _w in _security_warnings:
            logger.warning(f"[Security] {_w}")  # i18n
        logger.warning("[Security] The above anti-piracy layers are disabled by default. Enable them in .env for production. See BUSINESS_MODEL_FIXES.md FIX-02")  # i18n

    paid_license_sync_task = None
    sync_enabled = settings.PLUGIN_PAID_LICENSE_SYNC_ENABLED
    try:
        configured_interval = settings.PLUGIN_PAID_LICENSE_SYNC_INTERVAL_SECONDS
    except Exception as e:
        logger.warning(f"Invalid PLUGIN_PAID_LICENSE_SYNC_INTERVAL_SECONDS, using 0: {e}")
        configured_interval = 0
    try:
        fallback_interval = settings.PLUGIN_PAID_HOOK_LICENSE_RECHECK_SECONDS
    except Exception as e:
        logger.warning(f"Invalid PLUGIN_PAID_HOOK_LICENSE_RECHECK_SECONDS, using 0: {e}")
        fallback_interval = 0
    paid_license_sync_interval = configured_interval if configured_interval > 0 else fallback_interval
    if settings.PLUGIN_LICENSE_DAILY_CHECK_MODE:
        daily_interval = 86400
        if paid_license_sync_interval > 0:
            paid_license_sync_interval = max(paid_license_sync_interval, daily_interval)
        else:
            paid_license_sync_interval = daily_interval
    try:
        paid_license_sync_jitter = max(0, settings.PLUGIN_PAID_LICENSE_SYNC_JITTER_SECONDS)
    except Exception as e:
        logger.warning(f"Invalid PLUGIN_PAID_LICENSE_SYNC_JITTER_SECONDS, using 0: {e}")
        paid_license_sync_jitter = 0
    run_sync_on_startup = settings.PLUGIN_PAID_LICENSE_SYNC_ON_STARTUP

    if sync_enabled and paid_license_sync_interval > 0:
        async def _paid_license_sync_loop():
            if run_sync_on_startup:
                try:
                    cnt = plugin_manager.recheck_paid_plugins_licenses_now()
                    logger.info("Paid license sync (startup) finished: checked {} plugin(s)", cnt)
                except Exception as e:
                    logger.warning("Paid license sync (startup) failed: {}", e)
            while True:
                sleep_seconds = paid_license_sync_interval
                if paid_license_sync_jitter > 0:
                    sleep_seconds = max(1, paid_license_sync_interval + random.randint(-paid_license_sync_jitter, paid_license_sync_jitter))
                await asyncio.sleep(sleep_seconds)
                try:
                    cnt = plugin_manager.recheck_paid_plugins_licenses_now()
                    logger.debug("Paid license sync tick: checked {} plugin(s)", cnt)
                except Exception as e:
                    logger.warning("Paid license sync tick failed: {}", e)

        paid_license_sync_task = _watch_bg_task(_paid_license_sync_loop(), "paid_license_sync")

    # OSS 实例心跳上报
    oss_heartbeat_task = None
    oss_heartbeat_interval = 300
    try:
        oss_heartbeat_interval = max(60, settings.OSS_INSTANCE_HEARTBEAT_INTERVAL_SECONDS)
    except Exception as e:
        logger.warning(f"Failed to parse OSS heartbeat interval: {e}")
    if getattr(plugin_manager, "_oss_instance_id", None):
        async def _oss_heartbeat_loop():
            while True:
                await asyncio.sleep(oss_heartbeat_interval)
                try:
                    result = await plugin_manager.oss_instance_check_in()
                    if result.get("ok"):
                        logger.debug("OSS instance heartbeat ok")
                    else:
                        logger.warning("OSS instance heartbeat failed: {}", result.get("error"))
                except Exception as e:
                    logger.warning("OSS instance heartbeat error: {}", e)

        oss_heartbeat_task = _watch_bg_task(_oss_heartbeat_loop(), "oss_heartbeat")

    from app.sip.dialog_manager import dialog_manager
    from app.sip.ssrc_manager import ssrc_manager
    from app.sip.catalog_data_manager import catalog_data_manager
    try:
        await dialog_manager.restore_from_redis()
        logger.info("Startup step: dialog_manager.restore_from_redis done.")
    except Exception as e:
        logger.warning(f"Startup step: dialog_manager.restore_from_redis failed: {e}")
    _bg_dialog_cleanup = _watch_bg_task(dialog_manager.cleanup_loop(), "dialog_cleanup")
    _bg_ssrc_cleanup = _watch_bg_task(ssrc_manager.cleanup_loop(), "ssrc_cleanup")
    _bg_catalog_monitor = _watch_bg_task(catalog_data_manager.monitor_loop(), "catalog_monitor")

    # FIX [2026-07-29 P0]: 启动后自动补全缺失通道 — 后端重启后设备可能已注册但通道未同步
    # 等待 15 秒让设备重新注册，然后检查在线设备是否缺少通道，自动触发 catalog sync
    async def _startup_catalog_resync_loop():
        try:
            await asyncio.sleep(15)
            from app.db.session import AsyncSessionLocal
            from app.models.asset import Asset
            from app.models.resource import Resource
            from sqlalchemy import select, func
            from app.sip.handlers import _schedule_device_catalog_retry, get_device_last_seen_addr
            from app.sip.server import sip_server
            async with AsyncSessionLocal() as session:
                # 查找在线设备（status=1）及其通道数
                stmt = (
                    select(Asset, func.count(Resource.id).label("channel_count"))
                    .outerjoin(Resource, Resource.asset_id == Asset.id)
                    .where(Asset.status == 1)
                    .group_by(Asset.id)
                )
                result = await session.execute(stmt)
                rows = result.all()
                resync_count = 0
                for dev, ch_count in rows:
                    if ch_count == 0:
                        # 在线但无通道，需要重新同步
                        gb_id = getattr(dev, "gb_id", "") or ""
                        if not gb_id:
                            continue
                        # 优先从内存缓存获取设备地址（来自 Keepalive 源地址）
                        ip, port, proto = None, None, "UDP"
                        last_seen = get_device_last_seen_addr(gb_id)
                        if last_seen:
                            ip, port, proto = last_seen
                        else:
                            # 回退到数据库存储的地址
                            ip = getattr(dev, "ip_addr", "") or ""
                            port = getattr(dev, "port", 0) or 0
                            proto = getattr(dev, "transport", "UDP") or "UDP"
                        if not ip or not port:
                            logger.info(f"[STARTUP_RESYNC] Device {gb_id} online but no address info, skip")
                            continue
                        # 从 SIP server 获取 transport 对象
                        transport = None
                        try:
                            transport = sip_server.get_transport(ip, port, proto)
                        except Exception as _transport_err:
                            logger.debug(f"[STARTUP_RESYNC] get_transport error for {gb_id}: {_transport_err}")
                        if not transport:
                            logger.info(f"[STARTUP_RESYNC] Device {gb_id} no SIP transport for {ip}:{port}/{proto}, skip (will retry on next register)")
                            continue
                        transport_info = ((ip, port), proto, transport)
                        logger.info(f"[STARTUP_RESYNC] Device {gb_id} online with 0 channels, triggering catalog sync to {ip}:{port}/{proto}")
                        fire_and_forget(_schedule_device_catalog_retry(gb_id, transport_info))
                        resync_count += 1
                if resync_count > 0:
                    logger.info(f"[STARTUP_RESYNC] Triggered catalog sync for {resync_count} device(s) with missing channels")
        except Exception as e:
            logger.warning(f"[STARTUP_RESYNC] Failed to check missing channels: {e}")

    _bg_startup_resync = _watch_bg_task(_startup_catalog_resync_loop(), "startup_catalog_resync")

    # P1-fix [2026-07-17]: SIP Session Timer (RFC 4028) — 注册刷新/超时回调
    # on_refresh: refresher 方在 expires/2 时发送会话内 re-INVITE 保活
    # on_timeout: 非刷新方在 expires 超时未收到刷新时释放 SSRC/RTP 端口并终止会话
    async def _session_timer_refresh(call_id: str, from_tag: str, dialog) -> bool:
        """Session Timer 刷新回调：发送会话内 re-INVITE 保活。"""
        try:
            from app.sip.invite import sip_invite as _sip_invite_obj
            if _sip_invite_obj is None:
                logger.warning(f"session_timer_refresh: sip_invite not initialized for call_id={call_id}")
                return False
            return await _sip_invite_obj.send_session_refresh_reinvite(dialog)
        except Exception as e:
            logger.warning(f"session_timer_refresh: failed to send re-INVITE for call_id={call_id}: {e}")
            return False

    async def _session_timer_timeout(call_id: str, from_tag: str, dialog) -> None:
        """Session Timer 超时回调：释放 SSRC/RTP 端口/ZLM 流，防止僵尸会话。"""
        sd = getattr(dialog, "session_data", {}) or {}
        ssrc_val = str(sd.get("ssrc", "") or "").strip()
        stream_id_val = str(sd.get("stream_id", "") or "").strip()
        app_val = str(sd.get("app", "") or "").strip()
        node_id_val = str(sd.get("node_id", "") or "").strip()
        lease_id_val = str(sd.get("lease_id", "") or "").strip()
        logger.warning(
            f"session_timer_timeout: releasing resources for call_id={call_id} "
            f"ssrc={ssrc_val} stream={stream_id_val} app={app_val}"
        )
        # 释放 SSRC
        if ssrc_val:
            try:
                await ssrc_manager.release(ssrc_val)
            except Exception as e:
                logger.warning(f"session_timer_timeout: failed to release SSRC {ssrc_val}: {e}")
        # 关闭 ZLM 流
        if stream_id_val:
            try:
                from app.services.zlm_stream_control import close_zlm_stream as _close_stream
                await _close_stream(app=app_val, stream=stream_id_val, node_id=node_id_val or None)
            except Exception as e:
                logger.warning(f"session_timer_timeout: failed to close ZLM stream {stream_id_val}: {e}")
        # 释放端口租约
        if lease_id_val:
            try:
                from app.db.session import AsyncSessionLocal
                from app.core.media_nodes_db import release_lease
                async with AsyncSessionLocal() as _lease_session:
                    await release_lease(_lease_session, lease_id_val)
                    await _lease_session.commit()
            except Exception as e:
                logger.warning(f"session_timer_timeout: failed to release lease {lease_id_val}: {e}")

    try:
        dialog_manager.set_session_timer_callbacks(
            on_refresh=_session_timer_refresh,
            on_timeout=_session_timer_timeout,
        )
        logger.info("Startup step: session_timer callbacks registered.")
    except Exception as e:
        logger.warning(f"Startup step: failed to register session_timer callbacks: {e}")

    # FIX [2026-07-17 P1-E5]: 启动 invite_server_state 周期清理循环，
    # 清理僵尸 INVITE 服务端事务，防止内存泄漏。
    from app.sip.invite_server_state import invite_server_state as _iss

    async def _iss_cleanup_loop():
        while True:
            try:
                await asyncio.sleep(60)
                await _iss.cleanup_stale(max_age=300)
            except asyncio.CancelledError:
                break
            except Exception as _iss_err:
                logger.warning(f"invite_server_state cleanup error: {_iss_err}")
                await asyncio.sleep(10)

    _bg_iss_cleanup = _watch_bg_task(_iss_cleanup_loop(), "iss_cleanup")

    # FIX [2026-07-29 P0]: yield 外层加 try/finally，确保 CancelledError 时 shutdown 诊断代码也能执行。
    # 根因：uvicorn --workers 2 时第二个 worker 绑定 SIP 端口失败→崩溃→supervisor 关闭第一个 worker，
    # CancelledError 在 yield 处抛出，原代码 after-yield 不会执行，导致无法诊断 shutdown 原因。
    try:
        yield
    finally:
        # Shutdown
        # FIX [2026-07-29 P0]: 记录 shutdown 触发原因 — 是信号还是 CancelledError
        _sig = _shutdown_signal_received.get("signal")
        if _sig:
            _msg = f"[SHUTDOWN] Lifespan exiting yield — caused by {_sig} (pid={os.getpid()})"
        else:
            _msg = f"[SHUTDOWN] Lifespan exiting yield — no signal recorded, likely CancelledError/uvicorn worker shutdown (pid={os.getpid()})"
        logger.error(_msg)
        # 同步写入 stderr，绕过 loguru 异步 sink，确保进程被 kill 前诊断信息一定输出
        import sys as _sys
        _sys.stderr.write(_msg + "\n")
        _sys.stderr.flush()
        for _t in ("_bg_dialog_cleanup", "_bg_ssrc_cleanup", "_bg_catalog_monitor", "_bg_iss_cleanup", "_bg_startup_resync"):
            _task = locals().get(_t)
            if _task is not None:
                _task.cancel()
                try:
                    await _task
                except asyncio.CancelledError:
                    logger.debug("task_cancelled")
    # FIX: [2026-07-16 P1] R4-01/R4-02/R4-03/R4-06: 补全 shutdown 序列中遗漏的后台任务停止调用
    # 1. ha_cluster 订阅任务（Redis PubSub + _subscriber_task）
    try:
        from app.core.redis import ha_cluster
        ha_cluster.stop()
    except Exception as e:
        logger.warning(f"Shutdown step: ha_cluster stop failed (non-critical): {e}")
    # 2. storm_handler DB 更新 worker（_db_updater_worker）
    try:
        from app.sip.storm_handler import stop_storm_handler
        stop_storm_handler()
    except Exception as e:
        logger.warning(f"Shutdown step: storm_handler stop failed (non-critical): {e}")
    # 3. catalog_agg_prune 周期清理任务
    try:
        from app.sip.catalog import stop_catalog_agg_prune
        stop_catalog_agg_prune()
    except Exception as e:
        logger.warning(f"Shutdown step: catalog_agg_prune stop failed (non-critical): {e}")
    # 4. plugin license refresh subscriber
    try:
        plugin_manager.stop_license_refresh_subscriber()
    except Exception as e:
        logger.warning(f"Shutdown step: license_refresh_subscriber stop failed (non-critical): {e}")

    # FIX R23-SEVERE: 停止 catalog_runtime 周期性清理后台任务
    try:
        from app.sip.catalog_runtime import stop_catalog_runtime_cleanup
        stop_catalog_runtime_cleanup()
    except Exception as e:
        logger.warning(f"Shutdown step: catalog_runtime cleanup loop stop failed (non-critical): {e}")
    if paid_license_sync_task is not None:
        paid_license_sync_task.cancel()
        try:
            await paid_license_sync_task
        except asyncio.CancelledError:
            logger.debug("task_cancelled")
    if oss_heartbeat_task is not None:
        oss_heartbeat_task.cancel()
        try:
            await oss_heartbeat_task
        except asyncio.CancelledError:
            logger.debug("task_cancelled")

    try:
        _log_drain_task.cancel()
        await _log_drain_task
    except asyncio.CancelledError:
        logger.debug("task_cancelled")
    except NameError:
        logger.warning("NameError occurred")

    from app.services.tasks.task_manager import stop_all_background_tasks
    stop_task = asyncio.create_task(stop_all_background_tasks())
    try:
        await asyncio.wait_for(stop_task, timeout=10.0)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        logger.warning("(asyncio.TimeoutError, asyncio.CancelledError) occurred")
    except Exception as e:
        logger.warning(f"Stop background tasks failed: {e}")

    shutdown_task = asyncio.create_task(plugin_manager.emit(HOOK_ON_SHUTDOWN))
    try:
        await asyncio.wait_for(shutdown_task, timeout=10.0)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        logger.warning("shutdown task timeout or cancelled")
    except Exception as e:
        logger.warning(f"Shutdown hook failed: {e}")

    # G-08: 停止插件健康检查后台循环
    try:
        plugin_manager.stop_health_check_loop()
    except Exception as e:
        logger.warning(f"Stop health check loop failed: {e}")

    # OSS 实例从 Server 端注销
    try:
        await plugin_manager.deregister_oss_instance()
        logger.info("Shutdown step: OSS instance deregistered from marketplace server.")
    except Exception as e:
        logger.warning(f"Shutdown step: OSS instance deregister failed: {e}")

    await close_redis()
    await health_service.stop()
    try:
        from app.services.device_subscription_service import device_subscription_service
        await device_subscription_service.stop()
    except Exception as e:
        logger.warning(f"Stop device subscription service failed: {e}")
    try:
        from app.services.platform_subscription_service import platform_subscription_service
        await platform_subscription_service.stop()
    except Exception as e:
        logger.warning(f"Stop platform subscription service failed: {e}")
    await app_pkg.services.vision_hub.vision_hub.stop()
    await app_pkg.services.platform_service.platform_service.stop()
    await media_manager.stop()
    # P0-16 [2026-07-17]: 停止 VodQualityMonitor 清理循环，防止僵尸任务泄漏
    try:
        from app.services.vod_quality_monitor import vod_quality_monitor
        await vod_quality_monitor.stop()
    except Exception as e:
        logger.warning(f"Shutdown step: vod_quality_monitor stop failed (non-critical): {e}")
    await sip_server.stop()
    # FIX: [2026-07-17 P1] 取消所有 SIP watchdog 定时器，防止事件循环关闭后回调异常
    try:
        from app.sip.watchdog import cancel_all_watchdogs
        cancel_all_watchdogs()
        logger.info("Shutdown step: SIP watchdogs cancelled.")
    except Exception as e:
        logger.warning(f"Shutdown step: cancel_all_watchdogs failed (non-critical): {e}")
    try:
        from app.services.zlm_rtp_server_service import close_shared_zlm_client
        # FIX [2026-07-17 P1-D2]: 批量关闭所有活跃 RTP Server，防止 ZLM 端口泄漏。
        # 原问题：shutdown 时仅关闭 ZLM HTTP client，不调用 closeRtpServer，
        # 导致 ZLM 上残留 RTP Server 占用端口，重启后端口耗尽。
        try:
            from app.models.stream_session import StreamSession as _SS
            from sqlalchemy import select as _select
            from app.services.zlm_stream_control import close_zlm_stream
            import datetime as _dt
            async with AsyncSessionLocal() as _ss_db:
                # FIX [2026-07-22 P0]: 原查询 `_SS.status == "active"`，但 StreamSession
                # 模型没有 status 列（会话结束即删除行），导致批量 closeRtpServer 永不执行，
                # shutdown 后 ZLM 残留 RTP Server 占用端口。改为：行存在即视为活跃，
                # 限定最近 24h 创建的会话并上限 1000 条，避免历史脏行拖慢关停。
                # 注：start_time 为 naive DateTime，cutoff 用 naive UTC 避免 naive/aware 比较异常
                _cutoff = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None) - _dt.timedelta(hours=24)
                _active_sessions = (
                    await _ss_db.execute(
                        _select(_SS.app, _SS.stream, _SS.media_server_id)
                        .where(_SS.start_time >= _cutoff)
                        .limit(1000)
                    )
                ).all()
            if _active_sessions:
                _close_tasks = [
                    close_zlm_stream(app=str(r[0] or ""), stream=str(r[1] or ""), node_id=str(r[2] or "") or None)
                    for r in _active_sessions
                    if r[0] and r[1]
                ]
                await asyncio.gather(*_close_tasks, return_exceptions=True)
                logger.info(f"Shutdown step: batch closeRtpServer for {len(_close_tasks)} active sessions.")
        except Exception as _batch_close_err:
            logger.warning(f"Shutdown step: batch closeRtpServer failed (non-critical): {_batch_close_err}")
        await close_shared_zlm_client()
    except Exception as e:
        logger.warning(f"Close ZLM client failed: {e}")

    # FIX: [2026-07-17 P0] 取消所有 fire_and_forget 后台任务，
    # 防止 shutdown 时事件循环关闭导致 "Task was destroyed but it is pending!" 警告，
    # 并确保这些任务持有的 DB session、httpx 连接、SIP 事务锁等资源正确释放。
    try:
        from app.core.async_utils import _background_tasks
        _pending_bg = [t for t in _background_tasks if not t.done()]
        for _t in _pending_bg:
            _t.cancel()
        if _pending_bg:
            await asyncio.gather(*_pending_bg, return_exceptions=True)
            logger.info(f"Shutdown step: cancelled {len(_pending_bg)} fire-and-forget tasks.")
    except Exception as e:
        logger.warning(f"Shutdown step: fire_and_forget task cleanup failed (non-critical): {e}")

    # FIX: [2026-07-16 P1-A] 关闭共享 httpx 连接池，防止连接泄漏
    try:
        from app.core.http_client import close_http_client
        await close_http_client()
        logger.info("Shutdown step: shared HTTP client closed.")
    except Exception as e:
        logger.warning(f"Shutdown step: close_http_client failed: {e}")

    # FIX: [2026-07-16 P1-B] 取消 talk session cleanup 后台任务
    if _talk_cleanup_task is not None:
        _talk_cleanup_task.cancel()
        try:
            await _talk_cleanup_task
        except asyncio.CancelledError:
            logger.debug("Shutdown step: talk_cleanup_task cancelled.")
        except Exception as e:
            logger.warning(f"Shutdown step: talk_cleanup_task cancel failed: {e}")

    # FIX: [2026-07-16 P1-C] 关闭 HashChainSink 文件句柄，防止审计日志文件泄漏
    try:
        _audit_sink.stop()
        logger.info("Shutdown step: HashChainSink stopped.")
    except Exception as e:
        logger.warning(f"Shutdown step: HashChainSink.stop() failed: {e}")

_env = (settings.APP_ENV or "dev").lower()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.ENABLE_OPENAPI_DOCS else None,
    docs_url="/docs" if settings.ENABLE_OPENAPI_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_OPENAPI_DOCS else None,
    description="PyGBSentry API - Next Generation Video Surveillance Platform",
    version=settings.PROJECT_VERSION,  # 版本号从settings读取，与config.py保持一致
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
)

# OpenTelemetry tracing (optional, enabled via OTEL_ENABLED=true)
try:
    from app.core.tracing import setup_tracing
    setup_tracing(app=app)
except Exception as e:
    logger.warning(f"OpenTelemetry tracing setup failed (non-fatal): {e}")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        # 预计算 CSP connect-src 源列表：'self' + 自动推导的流媒体公网源 + 配置白名单。
        # SECURITY: 不再使用通配的 http:/https:/ws:/wss:，仅允许 'self' 和显式白名单。
        # 流媒体源从 STREAM_PUBLIC_SCHEME/HOST/PORT 自动推导（覆盖 FLV fetch / WHEP POST / WS-FLV）。
        self._csp_connect_sources = self._build_connect_sources()

    @staticmethod
    def _build_connect_sources() -> list:
        """构建 connect-src 源列表：'self' + 流媒体公网源(http+ws) + 配置白名单。"""
        sources = ["'self'"]

        # 自动推导 ZLMediaKit 流媒体公网源 — 前端播放 FLV/fMP4/WHEP/WS-FLV 时连接此源
        scheme = str(settings.STREAM_PUBLIC_SCHEME or "http").lower()
        stream_host = str(settings.STREAM_PUBLIC_HOST or "").strip()
        stream_port = settings.STREAM_PUBLIC_HTTP_PORT
        if stream_host:
            # 默认端口省略（http→80, https→443），避免冗余写法
            is_default_port = (scheme == "http" and stream_port == 80) or (
                scheme == "https" and stream_port == 443
            )
            host_part = stream_host if is_default_port else f"{stream_host}:{stream_port}"
            sources.append(f"{scheme}://{host_part}")
            # WebSocket 变体（WS-FLV / WSS-FLV）：http→ws, https→wss
            ws_scheme = "wss" if scheme == "https" else "ws"
            sources.append(f"{ws_scheme}://{host_part}")

        # 配置的额外白名单（ArcGIS 矢量瓦片、外置 ZLM 节点等）
        extra = str(settings.CSP_CONNECT_SRC_DOMAINS or "").strip()
        if extra:
            for part in extra.split(","):
                s = part.strip()
                if s:
                    sources.append(s)

        # 去重（保持顺序）
        seen = set()
        unique = []
        for s in sources:
            if s not in seen:
                seen.add(s)
                unique.append(s)
        return unique

    async def dispatch(self, request, call_next) -> Response:
        response: Response = await call_next(request)
        if not settings.ENABLE_SECURITY_HEADERS:
            return response

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        if settings.ENABLE_CROSS_ORIGIN_ISOLATION:
            response.headers.setdefault(
                "Cross-Origin-Embedder-Policy",
                str(settings.CROSS_ORIGIN_EMBEDDER_POLICY or "credentialless"),
            )

        # HSTS only when behind HTTPS
        try:
            if str(getattr(request.url, "scheme", "")).lower() == "https":
                response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        except Exception as e:
            logger.warning(f"Error: {e}")

        if settings.ENABLE_CSP:
            # SECURITY: nonce-based CSP — removes 'unsafe-inline' and 'unsafe-eval'.
            # A fresh nonce is generated per request and exposed via the X-CSP-Nonce
            # response header so templates/inline scripts can opt-in with nonce="{nonce}".
            import secrets as _secrets_csp
            _csp_nonce = _secrets_csp.token_urlsafe(16)
            try:
                request.state.csp_nonce = _csp_nonce
            except Exception as _csp_err:
                # FIX [2026-07-17 P3-2]: 描述性日志替代 "silently_swallowed_exception"
                logger.warning(f"Failed to set request.state.csp_nonce: {_csp_err}")
            response.headers.setdefault("X-CSP-Nonce", _csp_nonce)
            # SECURITY: connect-src 收紧 — 移除通配的 http:/https:/ws:/wss:，
            # 仅允许 'self' + 自动推导的流媒体公网源 + CSP_CONNECT_SRC_DOMAINS 白名单。
            # img-src 修正通配符（CSP 用 * 而非 ?）并补充 OSM 瓦片源。
            # 直接赋值（而非 setdefault）— 确保后端 CSP 覆盖 nginx 可能设置的限制性 CSP。
            # 当 nginx 已设置 CSP 时，setdefault 不会覆盖，导致浏览器同时执行两个 CSP
            # 策略（取交集），限制更严格的那个生效。直接赋值确保后端 CSP 始终生效。
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                + "base-uri 'self'; "
                + "frame-ancestors 'none'; "
                + "img-src 'self' data: blob: tile: https://*.tianditu.gov.cn https://*.is.autonavi.com https://*.bdimg.com https://*.arcgisonline.com https://tile.openstreetmap.org https://*.tile.openstreetmap.org; "
                + "media-src 'self' data: blob:; "
                + f"connect-src {' '.join(self._csp_connect_sources)}; "
                + f"script-src 'self' 'nonce-{_csp_nonce}'; "
                + f"style-src 'self' 'nonce-{_csp_nonce}'; "
                + "object-src 'none'; "
                + "worker-src 'self' blob:'"
            )

        return response


app.add_middleware(SecurityHeadersMiddleware)


# FIX: [2026-07-16 P0] Prometheus HTTP 请求指标中间件
# 原 metrics.py 定义了 http_requests_total Counter 但从未调用 .inc()，
# 导致 alert_rules.yml 中 PyGBSentryHighErrorRate 告警永不触发。
class HttpRequestMetricsMiddleware(BaseHTTPMiddleware):
    """记录每个 HTTP 请求的 method/endpoint/status_code 到 Prometheus Counter。"""

    async def dispatch(self, request, call_next) -> Response:
        try:
            response = await call_next(request)
            try:
                from app.core.metrics import http_requests_total
                # 使用路由模板而非实际 URL，避免 ID 产生 cardinality 爆炸
                endpoint = request.url.path
                # 尝试获取路由模板路径
                route = request.scope.get("route")
                if route and hasattr(route, "path"):
                    endpoint = route.path
                http_requests_total.labels(
                    method=request.method,
                    endpoint=endpoint,
                    status_code=str(response.status_code),
                ).inc()
            except Exception as _metric_err:
                # FIX [2026-07-17 P3-23]: 描述性日志替代静默吞异常
                logger.debug(f"Prometheus http_requests_total update failed: {_metric_err}")
            return response
        except Exception:
            raise

app.add_middleware(HttpRequestMetricsMiddleware)

# P1-08: HTTPS 强制重定向中间件 — 生产环境自动将 HTTP 请求重定向到 HTTPS
class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """生产环境强制 HTTPS：检查 X-Forwarded-Proto 头，非 HTTPS 请求 301 重定向。"""

    async def dispatch(self, request, call_next) -> Response:
        _is_prod = (settings.APP_ENV or "dev").lower() in {"prod", "production"}
        _force_https = settings.FORCE_HTTPS_IN_PRODUCTION
        if _is_prod and _force_https:
            # 检查 X-Forwarded-Proto（Nginx/ALB 等反向代理设置）
            fwd_proto = (request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
            if fwd_proto == "http":
                # 构建 HTTPS 重定向 URL
                from fastapi.responses import RedirectResponse
                original_url = str(request.url)
                https_url = original_url.replace("http://", "https://", 1)
                return RedirectResponse(url=https_url, status_code=301)
        return await call_next(request)


app.add_middleware(HTTPSRedirectMiddleware)

# ARCHITECTURE: API 版本协商中间件 — 为每个 /api/ 请求添加 X-API-Version 响应头，
# 对已弃用版本自动添加 Deprecation/Sunset/Link 头（见 app.api.versioning）
from app.api.versioning import APIVersionMiddleware
app.add_middleware(APIVersionMiddleware)

# Production safety checks: refuse known default secrets
# Note: config.py 中已有先序检查（SystemExit），此处为兜底防护（RuntimeError）
import os as _os

# Common weak passwords list
# P2-22: 内置基线 + 外部文件扩展（支持 HaveIBeenPwned 下载的密码列表）
_DEFAULT_PASSWORDS = {
    "password", "12345678", "admin", "root", "administrator",
    "123456", "123456789", "1234567890", "admin123", "admin1234",
    "Abc12345", "Passw0rd", "Passw0rd!", "rootroot", "testtest",
    # FIX: [2026-07-16 P1] 添加模式化/示例占位密钥到已知弱密钥集合
    "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0",  # 顺序字母+数字交替
    "***REMOVED***",  # 项目名+年份示例
    "pygbsentry-secret-key",
    "change_me_generate_a_strong_password",
    "change_me",
}

# P2-22: 从外部文件加载额外弱密码（每行一个，# 开头为注释）
# 用法：在 .env 中设置 WEAK_PASSWORD_LIST_FILE=/path/to/weak_passwords.txt
# 可从 HaveIBeenPwned 下载密码列表（https://haveibeenpwned.com/Passwords）
_weak_list_file = str(settings.WEAK_PASSWORD_LIST_FILE or "").strip()
if _weak_list_file and _os.path.exists(_weak_list_file):
    try:
        _loaded_count = 0
        with open(_weak_list_file, "r", encoding="utf-8", errors="replace") as _f:
            for _line in _f:
                _pwd = _line.strip().lower()
                if _pwd and not _pwd.startswith("#"):
                    _DEFAULT_PASSWORDS.add(_pwd)
                    _loaded_count += 1
        logger.info(f"P2-22: Loaded {_loaded_count} additional weak passwords from {_weak_list_file} (total: {len(_DEFAULT_PASSWORDS)})")
    except Exception as _e:
        logger.warning(f"P2-22: Failed to load weak password list from {_weak_list_file}: {_e}")

def _is_weak_secret(key_value: str) -> bool:
    """Check if a secret key is obviously weak (too short, all same char, sequential, or in common list)."""
    if not key_value:
        return True
    if len(key_value) < 16:
        return True
    lower = key_value.lower()
    if lower in _DEFAULT_PASSWORDS:
        return True
    # All same character
    if len(set(key_value)) == 1:
        return True
    # Sequential characters (e.g., "abcdef...", "123456...")
    if lower in "abcdefghijklmnopqrstuvwxyz" or lower in "0123456789":
        return True
    # FIX: [2026-07-16 P1] 检测模式化密钥：字母+数字交替（如 a1b2c3...）
    # 此类密钥虽然长度足够但可预测性极高
    import re as _re
    # 形如 "a1b2c3d4..." 的交替模式
    if _re.fullmatch(r"([a-z][0-9])+|[0-9]([a-z][0-9])+", lower) and len(key_value) >= 16:
        return True
    # 形如 "key-2024" / "secret-2026" 等项目名+年份模式
    if _re.fullmatch(r"[a-z]+-?(secret|key|password)-?\d{2,4}", lower):
        return True
    # 含 "change_me" 占位符的密钥
    if "change_me" in lower or "changeme" in lower:
        return True
    return False

if (settings.APP_ENV or "dev").lower() in {"prod", "production"}:
    if _is_weak_secret(settings.SECRET_KEY):
        raise RuntimeError("SECURITY: SECRET_KEY is empty, too short, or using a weak/default value. Please set a strong SECRET_KEY (32+ chars) via environment variable in production.")
    if _is_weak_secret(settings.MEDIA_SERVER_SECRET):
        raise RuntimeError("SECURITY: MEDIA_SERVER_SECRET is empty, too short, or using a weak/default value. Please set a strong MEDIA_SERVER_SECRET via environment variable in production.")
    _db_type = (settings.DATABASE_TYPE or "").lower()
    if _db_type not in {"sqlite"}:
        for _pwd_key in ["POSTGRES_PASSWORD", "DATABASE_PASSWORD"]:
            _pwd_val = str(getattr(settings, _pwd_key, "") or "").strip().lower()
            if _pwd_val in _DEFAULT_PASSWORDS or _pwd_val == "":
                raise RuntimeError(f"SECURITY: {_pwd_key} is using a default or empty password. Please set a strong password in production.")
    _sip_pwd = str(settings.SIP_DEFAULT_PASSWORD or "").strip().lower()
    if _sip_pwd in _DEFAULT_PASSWORDS or _sip_pwd == "":
        raise RuntimeError("SECURITY: SIP_DEFAULT_PASSWORD is using a default or empty password. Please set a strong password in production.")
    if settings.ALLOW_PUBLIC_REGISTRATION:
        raise RuntimeError("SECURITY: ALLOW_PUBLIC_REGISTRATION is enabled, which may allow unauthorized user registration. It is recommended to disable public registration in production.")
else:
    if _is_weak_secret(settings.SECRET_KEY):
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "SECRET_KEY is not set or is weak; each restart generates a new key, invalidating all JWTs. "
            "It is recommended to set a fixed, strong SECRET_KEY (32+ chars) in .env."
        )

# Init Rate Limiter
init_rate_limiter(app)

# Set all CORS enabled origins
if settings.BACKEND_CORS_ORIGINS:
    _cors_env = (settings.APP_ENV or "dev").lower()
    # FIX: [2026-08-22 P3] 规范化 Origin：浏览器 Origin 头按规范永不含尾部斜杠，
    # 配置写成 "http://domain/" 时 Starlette 精确匹配永不命中 → CORS 全部拒绝
    # （测试发现）。统一 rstrip("/") 消除该配置陷阱。
    _cors_origins = [str(origin).rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS]
    if _cors_env in {"prod", "production"}:
        # Exact hostname matching to prevent bypass (e.g., "mylocalhost.com")
        from urllib.parse import urlparse as _urlparse
        for origin in _cors_origins:
            parsed = _urlparse(origin)
            hostname = (parsed.hostname or "").lower()
            if hostname in ("localhost", "127.0.0.1", "::1"):
                raise RuntimeError(
                    f"SECURITY: BACKEND_CORS_ORIGINS contains '{origin}' with localhost/loopback "
                    f"address, which is not allowed in production.\n"
                    f"HINT: Set BACKEND_CORS_ORIGINS to your public frontend URL "
                    f"(e.g., BACKEND_CORS_ORIGINS=[\"https://your-domain.com\"]).\n"
                    f"If nginx proxies /api/ to the backend (same-origin), you can leave "
                    f"BACKEND_CORS_ORIGINS empty — CORS is not needed.\n"
                    f"Edit the .env file and restart the backend."
                )
        # W-09 生产环境CORS禁止通配符*，防止跨域安全策略失效
        if any(o.strip() == "*" for o in _cors_origins):
            raise RuntimeError(
                "SECURITY: BACKEND_CORS_ORIGINS must not contain wildcard '*' in production.\n"
                "HINT: Set BACKEND_CORS_ORIGINS to explicit public frontend URL(s) instead."
            )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        # FIX: [2026-07-16 P1] 移除 "Origin" — CORS 规范明确排除该头部不应出现在
        # Access-Control-Allow-Headers 中（浏览器自动设置，不应声明）。
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With", "X-API-Key", "X-Sensitive-Operation"],
        # FIX: [2026-07-16 P1] 添加 max_age，缓存预检结果 10 分钟，减少 OPTIONS 请求
        max_age=600,
    )

from app.core.exceptions import AppException

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )

# ZlmApiError继承RuntimeError但有status_code字段，添加异常处理器使FastAPI正确响应
from app.services.zlm_rtp_server_service import ZlmApiError

@app.exception_handler(ZlmApiError)
async def zlm_api_error_handler(request: Request, exc: ZlmApiError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": str(exc),
            "message": str(exc),
            "operation": exc.operation,
            "category": exc.category,
            "hint": exc.hint,
            "retryable": exc.retryable,
        },
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail: object = exc.detail
    if isinstance(detail, dict):
        payload = dict(detail)
        message = str(payload.get("message") or payload.get("detail") or "Request failed")
        payload.setdefault("detail", message)
        payload.setdefault("message", message)
        payload.setdefault("status_code", exc.status_code)
        payload.setdefault("error_code", payload.get("error_code", f"ERR_{exc.status_code}"))
        return JSONResponse(status_code=exc.status_code, content=payload)
    message = str(detail or "Request failed")
    if exc.status_code == 405:
        message = "Method not allowed"
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": message, "message": message, "status_code": exc.status_code, "error_code": f"ERR_{exc.status_code}"},
    )

@app.exception_handler(StarletteHTTPException)
async def starlette_exception_handler(request: Request, exc: StarletteHTTPException):
    message = str(exc.detail or "Request failed")
    if exc.status_code == 405:
        message = "Method not allowed"
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": message, "message": message, "status_code": exc.status_code, "error_code": f"ERR_{exc.status_code}"},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.opt(exception=True).error("Global error: {}", exc)
    _env = (settings.APP_ENV or "dev").lower()
    if _env in {"prod", "production"}:
        detail_msg = "Internal server error"
    else:
        detail_msg = str(exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "message": detail_msg,
            "error_code": "ERR_001",
            "retryable": True,
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        },
    )

def _sanitize_validation_error_value(value):
    """递归清洗校验错误中的值，确保可 JSON 序列化。

    FIX: [2026-08-22 P1] pydantic v2 中 @validator 抛出的 ValueError 等异常对象会
    进入 error['ctx']（如 {'error': ValueError(...)}），原样放入 JSONResponse 的
    content 触发 JSON 序列化失败 → 500。基本类型保留，dict/list 递归，其余转 str。
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _sanitize_validation_error_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_validation_error_value(v) for v in value]
    return str(value)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [
        _sanitize_validation_error_value(e) if isinstance(e, dict) else str(e)
        for e in (exc.errors() or [])
    ]
    detail = "Validation error"
    if errors:
        loc = errors[0].get("loc", [])
        if len(loc) > 1 and isinstance(loc[-1], str):
            detail = f"Parameter '{loc[-1]}' validation failed"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": detail, "error_code": "ERR_002", "errors": errors},
    )

app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(common_channel_router, prefix="/api/common/channel")
app.include_router(play_start_router, prefix="/api/play")

@app.get("/")
async def root():
    data = {"message": "Welcome to PyGBSentry"}
    if app.docs_url:
        data["docs"] = app.docs_url
    return data


@app.get("/health")
@app.get("/api/v1/health/")
async def health():
    """无鉴权健康检查，供负载均衡/容器探针使用。检查 DB + Redis + SIP 关键服务状态。"""
    import time as _health_time
    from datetime import datetime, timezone
    checks: dict[str, object] = {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    # DB check (critical) — 记录延迟
    _t0 = _health_time.time()
    try:
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok", "latency_ms": round((_health_time.time() - _t0) * 1000, 1)}
    except Exception as e:
        checks["status"] = "degraded"
        checks["database"] = {"status": "error", "error": str(e)[:200]}
    # Check Redis: distinguish "not configured" vs "configured but unreachable"
    _t1 = _health_time.time()
    try:
        from app.core.redis import redis_client as _rc
        if _rc is not None:
            await _rc.ping()
            checks["redis"] = {"status": "ok", "latency_ms": round((_health_time.time() - _t1) * 1000, 1)}
        else:
            checks["redis"] = {"status": "not_configured"}
    except Exception as e:
        checks["redis"] = {"status": "error", "error": str(e)[:200]}
        if checks["status"] == "ok":
            checks["status"] = "degraded"
    # SIP check — reports whether the SIP signaling server is running
    try:
        checks["sip"] = {"status": "running" if sip_server.running else "stopped"}
    except Exception as e:
        checks["sip"] = {"status": "error", "error": str(e)[:200]}
    # FIX: [2026-07-04] 健康检查仅读取配置的 media_nodes 数量并硬编码 status=ok，
    # 未实际探测 ZLM 端口/HTTP API，导致 ZLM 未运行时仍报告 ok。改为调用
    # media_manager.is_running() 执行真实 HTTP 探活。 [全栈工程师]
    try:
        from app.core.media_nodes import get_media_nodes
        _nodes = get_media_nodes()
        _zlm_running = await media_manager.is_running()
        checks["zlm"] = {
            "total_nodes": len(_nodes),
            "online_nodes": 1 if _zlm_running else 0,
            "status": "ok" if _zlm_running else "down",
        }
        if not _zlm_running and checks["status"] == "ok":
            checks["status"] = "degraded"
    except Exception as e:
        checks["zlm"] = {"status": "error", "error": str(e)[:200]}
    # P3-06: Plugin check — 报告已加载插件数
    try:
        _plugin_count = len(plugin_manager.list_plugins()) if hasattr(plugin_manager, "list_plugins") else 0
        checks["plugins"] = {"loaded": _plugin_count, "status": "ok"}
    except Exception:
        checks["plugins"] = {"status": "unknown"}
    status_code = 200 if checks["status"] == "ok" else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(content=checks, status_code=status_code)


@app.get("/health/ready")
async def health_ready():
    """Readiness probe: delegates to the shared readiness implementation.

    P1-33: Previously duplicated the readiness logic inline (DB + Redis probes).
    Now backed by the same single source of truth as ``/api/v1/health/readiness``
    (defined in ``app.api.v1.endpoints.health``), so both paths return identical
    results driven by ``health_service.is_ready``.
    """
    from app.api.v1.endpoints.health import build_readiness_response
    return build_readiness_response()


@app.get("/health/live")
@app.get("/api/v1/health/liveness")
async def health_live():
    """Liveness probe: checks if the process is alive (lightweight, no external dependency checks)."""
    return {"status": "alive"}


@app.get("/metrics")
async def metrics(request: Request):
    """Prometheus metrics endpoint — IP whitelist protected."""
    # IP whitelist for metrics endpoint
    client_ip = request.client.host if request.client else "unknown"
    allowed_networks = settings.METRICS_ALLOWED_NETWORKS
    import ipaddress
    allowed = False
    for net in allowed_networks:
        try:
            if ipaddress.ip_address(client_ip) in ipaddress.ip_network(net, strict=False):
                allowed = True
                break
        except ValueError:
            continue
    if not allowed:
        raise HTTPException(status_code=403, detail="Metrics access denied")
    # 添加Prometheus指标暴露端点
    from app.core.metrics import metrics_response
    from prometheus_client import CONTENT_TYPE_LATEST
    from starlette.responses import Response
    return Response(content=metrics_response(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    import uvicorn
    port = settings.BACKEND_PUBLIC_PORT
    # FIX: [2026-07-16 P0] 原生产环境绑定 127.0.0.1 导致 Docker 容器不可达：
    # docker-compose.yml 默认 APP_ENV=prod，触发 127.0.0.1 绑定，
    # Docker 端口映射无法将流量转发到容器内的 127.0.0.1，服务完全不可达。
    # 当显式设置 BACKEND_BIND_HOST 时使用该值；
    # Docker 环境（检测到 /.dockerenv 或 RUNNING_IN_DOCKER=true）绑定 0.0.0.0；
    # 非 Docker 的生产环境仍默认 127.0.0.1 以保留反向代理场景的安全默认。
    _docker_env = (
        bool(os.environ.get("RUNNING_IN_DOCKER"))
        or os.path.exists("/.dockerenv")
    )
    _explicit_host = os.environ.get("BACKEND_BIND_HOST")
    if _explicit_host:
        _host = _explicit_host
    elif _docker_env:
        _host = "0.0.0.0"
    elif _env in {"prod", "production"}:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "PRODUCTION: binding backend to 127.0.0.1 (not 0.0.0.0) for security. "
            "Use a reverse proxy (nginx) for external access, or set BACKEND_BIND_HOST=0.0.0.0."
        )
        _host = "127.0.0.1"
    else:
        _host = "0.0.0.0"
    uvicorn.run("app.main:app", host=_host, port=port, reload=_env == "dev", loop="asyncio", timeout_keep_alive=settings.UVICORN_TIMEOUT_KEEP_ALIVE)
