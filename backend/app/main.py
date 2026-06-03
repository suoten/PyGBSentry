# -------------------------------------------------------------------------
# 🚀 Project: PyGBSentry
# ✍️ Author: suoten
# 📧 Email: suoten@163.com
# 📄 License: AGPL-3.0-or-later WITH Classpath-Exception
# -------------------------------------------------------------------------

from contextlib import asynccontextmanager
from loguru import logger
import asyncio
import random
import sys
import os

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

# Configure Loguru
from app.core.config import settings as _settings_for_log
_log_format_env = getattr(_settings_for_log, "LOG_FORMAT", None) or os.environ.get("LOG_FORMAT", "text").lower()
if _log_format_env == "json":
    _log_format = '{"timestamp":"{time:YYYY-MM-DD HH:mm:ss.SSS}","level":"{level}","module":"{name}","function":"{function}","line":{line},"message":"{message}"}'
else:
    _log_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
_log_dir = getattr(_settings_for_log, "LOG_DIR", None) or "logs"
logger.remove()
logger.add(sys.stderr, level="INFO", format=_log_format, enqueue=True)
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
        except Exception:
            pass  # Start fresh if recovery fails
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
            except Exception:
                pass

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
                self._file.close()
                # Rename current file with timestamp
                import datetime as _dt
                ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                rotated_path = f"{self._path}.{ts}"
                try:
                    os.rename(self._path, rotated_path)
                except OSError:
                    pass
                # Preserve hash chain continuity: write a chain-link entry
                # in the new file referencing the last hash from the rotated file
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
        except Exception:
            pass

    def stop(self) -> None:
        with self._lock:
            if self._file and not self._file.closed:
                self._file.close()

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass

logger.add(f"{_log_dir}/app.log", rotation="50 MB", retention="180 days", compression="gz", level="INFO", format=_log_format, enqueue=True)  # 日志保留180天(等保2.0三级要求)
# 日志防篡改 — 哈希链审计日志，每条日志包含前一条的SHA256摘要
_audit_sink = HashChainSink(f"{_log_dir}/audit.log")
logger.add(_audit_sink.write, level="WARNING", filter=lambda record: record["level"].no >= 30, enqueue=True)

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
_root.setLevel(logging.DEBUG)
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
from sqlalchemy import text
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
    SQLite 下先 PRAGMA busy_timeout，减轻与其它进程抢锁时的长阻塞。
    """
    async with AsyncSessionLocal() as db:
        if (getattr(engine.dialect, "name", None) or "").lower() == "sqlite":
            await db.execute(text(f"PRAGMA busy_timeout={settings.SQLITE_BUSY_TIMEOUT_MS}"))
        return await fn(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Using Database Dialect: {engine.dialect.name}")

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
            logger.debug(f"alembic stamp pre-check error: {_stamp_check_err}")

        if _need_stamp:
            logger.info("Startup step: stamping alembic version (database has tables but no alembic_version)...")
            try:
                _stamp_result = subprocess.run(
                    [sys.executable, "-m", "alembic", "stamp", "head"],
                    cwd=_backend_dir,
                    capture_output=True, text=True, timeout=30,
                )
                if _stamp_result.returncode == 0:
                    logger.info("Startup step: alembic stamp head done.")
                else:
                    logger.warning(f"alembic stamp head failed: {_stamp_result.stderr[-300:]}")
            except Exception as _stamp_err:
                logger.warning(f"alembic stamp head error: {_stamp_err}")

        logger.info("Startup step: alembic upgrade head...")
        # FIXED-P0: 使用 subprocess 调用 alembic CLI，而非 import alembic.env
        # alembic/env.py 中 `from alembic import context` 引用第三方库，
        # 本地 alembic/ 目录会导致命名冲突，无论用 import 还是 importlib 都无法避免
        try:
            _result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=_backend_dir,
                capture_output=True, text=True, timeout=120,
            )
            if _result.returncode == 0:
                logger.info("Startup step: alembic upgrade head done.")
            else:
                _stderr = _result.stderr or ""
                logger.error(f"alembic upgrade head failed (exit {_result.returncode}): {_stderr[-500:]}")
                # FIXED-P0: upgrade 失败且错误是"表已存在"时，自动 stamp head
                # 场景：alembic_version 有旧版本号，但表已由 ensure_business_schema 创建
                _dup_keywords = ("already exists", "DuplicateTable", "DuplicateColumn", "DuplicateObject")
                if any(kw.lower() in _stderr.lower() for kw in _dup_keywords):
                    logger.warning("Detected 'already exists' error — stamping alembic to head and continuing...")
                    try:
                        _stamp_result = subprocess.run(
                            [sys.executable, "-m", "alembic", "stamp", "head"],
                            cwd=_backend_dir,
                            capture_output=True, text=True, timeout=30,
                        )
                        if _stamp_result.returncode == 0:
                            logger.info("Startup step: alembic stamp head done (after duplicate error).")
                        else:
                            logger.warning(f"alembic stamp head failed: {_stamp_result.stderr[-300:]}")
                    except Exception as _stamp_err:
                        logger.warning(f"alembic stamp head error: {_stamp_err}")
        except subprocess.TimeoutExpired:
            logger.error("alembic upgrade head timed out (120s)")
        except Exception as _alembic_err:
            logger.error(f"alembic upgrade head error: {_alembic_err}")

        # FIXED-P0: alembic stamp head 只标记版本号，不创建缺失的表
        # 当数据库由 ensure_business_schema 部分创建时，某些表（如 ip_blacklist）
        # 可能不在 ensure_business_schema 的 SQL 列表中但存在于 ORM 模型中
        # 用 Base.metadata.create_all 兜底补建所有缺失的表
        try:
            from app.models.model_registry import Base
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Startup step: ensure all ORM tables exist (create_all fallback) done.")
        except Exception as _create_all_err:
            logger.warning(f"Startup step: create_all fallback error: {_create_all_err}")
    else:
        logger.info("Startup step: ensure_business_schema...")
        await ensure_business_schema()
        logger.info("Startup step: ensure_business_schema done.")

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
    plugin_manager.load_plugins()
    logger.info("Startup step: plugin_manager.load_plugins done.")
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
    if bool(getattr(settings, "PLUGIN_MARKETPLACE_ENABLED", False)):
        try:
            from app.services.license_service import _get_current_machine_code
            _machine_code = _get_current_machine_code()
            await plugin_manager.register_oss_instance(machine_code=_machine_code)
            logger.info("Startup step: OSS instance registered to marketplace server.")
        except Exception as e:
            logger.warning(f"Startup step: OSS instance register failed: {e}, continue startup.")

    # 续费即时推送：订阅 Redis license:refresh 频道（仅在 PLUGIN_MARKETPLACE_ENABLED=True 时启用）
    if bool(getattr(settings, "PLUGIN_MARKETPLACE_ENABLED", False)):
        try:
            asyncio.create_task(plugin_manager.start_license_refresh_subscriber())
            logger.info("Startup step: license refresh Redis subscriber started.")
        except Exception as e:
            logger.warning(f"Startup step: license refresh subscriber failed: {e}, continue startup.")
    else:
        logger.info("Startup step: PLUGIN_MARKETPLACE_ENABLED=False, marketplace integration disabled.")

    # 业务/行政区 parent 拆分迁移：默认不在启动时执行，避免 SQLite 锁等待拖死整站（与旧版「顺畅启动」一致）
    if not bool(getattr(settings, "RUN_SPLIT_CATALOG_MIGRATIONS_ON_STARTUP", False)):
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
    if not bool(getattr(settings, "RUN_REGION_SEED_ON_STARTUP", False)):
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
    if not bool(getattr(settings, "ENSURE_EMBEDDED_MEDIA_NODE_ON_STARTUP", False)):
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

    # SipStateBackend 主动初始化（触发 get_sip_state_backend() 确定后端类型）
    try:
        from app.sip.state_backend import get_sip_state_backend as _get_sip_state_backend
        _backend = _get_sip_state_backend()
        _backend_type = type(_backend).__name__
        logger.info(f"Startup step: SipStateBackend initialized (type={_backend_type})")
    except Exception as e:
        logger.warning(f"Startup step: SipStateBackend init failed: {e}, continue startup.")

    # SECRET 一致性校验：对比 settings.MEDIA_SERVER_SECRET 与 DB 中 MediaNode.secret
    try:
        async def _check_secret_consistency(db):
            from app.models.media_node import MediaNode as _MN
            from sqlalchemy import select as _sel
            result = await db.execute(_sel(_MN.id, _MN.secret).where(_MN.is_embedded == True).limit(1))
            row = result.first()
            return row

        secret_row = await asyncio.wait_for(_session_call(_check_secret_consistency), timeout=10)
        if secret_row and secret_row[1] and secret_row[1] != settings.MEDIA_SERVER_SECRET:
            _app_env = (getattr(settings, "APP_ENV", "dev") or "dev").lower()
            if _app_env in {"prod", "production"}:
                logger.error(
                    "FATAL: MEDIA_SERVER_SECRET mismatch with DB MediaNode.secret (node_id=%s). "
                    "ZLM API calls will FAIL. Please ensure MEDIA_SERVER_SECRET in .env matches the secret in DB media_nodes table, "
                    "or run 'python scripts/update_media_node_secret.py' to sync DB with .env.",
                    secret_row[0],
                )
                raise RuntimeError(
                    "MEDIA_SERVER_SECRET mismatch between .env and DB MediaNode.secret (node_id=%s). "
                    "ZLM API calls will fail. Please fix and restart." % secret_row[0]
                )
            else:
                logger.warning(
                    "MEDIA_SERVER_SECRET mismatch with DB MediaNode.secret (node_id=%s). "
                    "ZLM API calls may fail. This is acceptable in dev, but please ensure they match.",
                    secret_row[0],
                )
    except asyncio.TimeoutError:
        logger.warning("Startup step: secret consistency check timeout (10s), skipped.")
    except Exception as e:
        logger.debug("Startup step: secret consistency check skipped: %s", e)

    # Print required ports and (optionally) auto-open firewall rules
    logger.info("Startup step: ensure_firewall_ports...")
    try:
        ensure_firewall_ports()
        logger.info("Startup step: ensure_firewall_ports done.")
    except Exception as e:
        logger.warning(f"Startup step: ensure_firewall_ports failed: {e}")

    if not bool(getattr(settings, "INIT_REDIS_ON_STARTUP", False)):
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
            else:
                for t in pending:
                    t.cancel()
                logger.warning("Startup step: init_redis timeout (10s). Continue startup without Redis.")
        except Exception as e:
            logger.warning(f"Startup step: init_redis failed: {e}. Continue startup without Redis.")

    logger.info("Startup step: init_handlers...")
    init_handlers()
    logger.info("Startup step: init_handlers done.")

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
        if bool(getattr(settings, "SIP_STARTUP_REQUIRED", True)):
            logger.error("Startup step: sip_server.start timeout (20s), abort startup.")
            raise
        logger.warning("Startup step: sip_server.start timeout (20s), continue startup without SIP.")
    except OSError as e:
        if bool(getattr(settings, "SIP_STARTUP_REQUIRED", True)):
            logger.error(f"Startup step: sip_server.start failed: {e}. abort startup.")
            raise
        logger.warning(f"Startup step: sip_server.start failed: {e}. Continue startup without SIP.")

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
        logger.debug(f"Startup step: cluster subscriber start failed (non-critical): {e}")

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
        logger.debug(f"Startup step: catalog_agg_prune start failed (non-critical): {e}")

    # Start AI Vision Hub
    app_pkg.services.vision_hub.vision_hub = VisionHub()
    logger.info("Startup step: vision_hub.start...")
    try:
        await asyncio.wait_for(app_pkg.services.vision_hub.vision_hub.start(), timeout=20)
        logger.info("Startup step: vision_hub.start done.")
    except asyncio.TimeoutError:
        logger.warning("Startup step: vision_hub.start timeout (20s), continue startup.")

    # Start Embedded ZLMediaKit（首次源码编译可能极久，默认 EMBEDDED_ZLM_START_TIMEOUT_SECONDS=3600）
    zlm_boot_timeout = int(getattr(settings, "EMBEDDED_ZLM_START_TIMEOUT_SECONDS", 3600) or 0)
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
    from app.services.tasks.task_manager import start_all_background_tasks
    await start_all_background_tasks(plugin_manager=plugin_manager)

    # Start talk session cleanup loop
    _talk_cleanup_task = None
    try:
        from app.sip.talk import start_talk_cleanup_loop
        _talk_cleanup_task = asyncio.create_task(start_talk_cleanup_loop())
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
            except Exception:
                await asyncio.sleep(1)

    _log_drain_task = asyncio.create_task(_drain_log_queue(log_manager, _get_log_queue))
    logger.info("Startup step: log queue drainer started.")

    logger.info("Startup complete.")

    _security_warnings = []
    if not getattr(settings, "PLUGIN_LICENSE_MACHINE_CODE_ENABLED", False):
        _security_warnings.append("PLUGIN_LICENSE_MACHINE_CODE_ENABLED=False: machine code binding disabled, license can be copied across machines")  # i18n
    if not getattr(settings, "PLUGIN_LICENSE_ACTIVATION_TOKEN_ENABLED", False):
        _security_warnings.append("PLUGIN_LICENSE_ACTIVATION_TOKEN_ENABLED=False: activation token disabled, trial period can be reset")  # i18n
    if not getattr(settings, "PLUGIN_PACKAGE_INTEGRITY_REQUIRED_IN_PROD", False):
        _security_warnings.append("PLUGIN_PACKAGE_INTEGRITY_REQUIRED_IN_PROD=False: package signature verification disabled, plugin packages can be tampered")  # i18n
    if _security_warnings and (getattr(settings, "APP_ENV", "dev") or "dev").lower() in {"prod", "production"}:
        for _w in _security_warnings:
            logger.warning("[Security] %s", _w)  # i18n
        logger.warning("[Security] The above anti-piracy layers are disabled by default. Enable them in .env for production. See BUSINESS_MODEL_FIXES.md FIX-02")  # i18n

    paid_license_sync_task = None
    sync_enabled = bool(getattr(settings, "PLUGIN_PAID_LICENSE_SYNC_ENABLED", True))
    try:
        configured_interval = int(getattr(settings, "PLUGIN_PAID_LICENSE_SYNC_INTERVAL_SECONDS", 0) or 0)
    except Exception:
        configured_interval = 0
    try:
        fallback_interval = int(getattr(settings, "PLUGIN_PAID_HOOK_LICENSE_RECHECK_SECONDS", 60) or 0)
    except Exception:
        fallback_interval = 0
    paid_license_sync_interval = configured_interval if configured_interval > 0 else fallback_interval
    if bool(getattr(settings, "PLUGIN_LICENSE_DAILY_CHECK_MODE", False)):
        daily_interval = 86400
        if paid_license_sync_interval > 0:
            paid_license_sync_interval = max(paid_license_sync_interval, daily_interval)
        else:
            paid_license_sync_interval = daily_interval
    try:
        paid_license_sync_jitter = max(0, int(getattr(settings, "PLUGIN_PAID_LICENSE_SYNC_JITTER_SECONDS", 5) or 0))
    except Exception:
        paid_license_sync_jitter = 0
    run_sync_on_startup = bool(getattr(settings, "PLUGIN_PAID_LICENSE_SYNC_ON_STARTUP", True))

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

        paid_license_sync_task = asyncio.create_task(_paid_license_sync_loop())

    # OSS 实例心跳上报
    oss_heartbeat_task = None
    oss_heartbeat_interval = 300
    try:
        oss_heartbeat_interval = max(60, int(getattr(settings, "OSS_INSTANCE_HEARTBEAT_INTERVAL_SECONDS", 300) or 300))
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

        oss_heartbeat_task = asyncio.create_task(_oss_heartbeat_loop())

    from app.sip.dialog_manager import dialog_manager
    from app.sip.ssrc_manager import ssrc_manager
    from app.sip.catalog_data_manager import catalog_data_manager
    try:
        await dialog_manager.restore_from_redis()
        logger.info("Startup step: dialog_manager.restore_from_redis done.")
    except Exception as e:
        logger.warning(f"Startup step: dialog_manager.restore_from_redis failed: {e}")
    _bg_dialog_cleanup = asyncio.create_task(dialog_manager.cleanup_loop())
    _bg_ssrc_cleanup = asyncio.create_task(ssrc_manager.cleanup_loop())
    _bg_catalog_monitor = asyncio.create_task(catalog_data_manager.monitor_loop())

    yield
    # Shutdown
    for _t in ("_bg_dialog_cleanup", "_bg_ssrc_cleanup", "_bg_catalog_monitor"):
        _task = locals().get(_t)
        if _task is not None:
            _task.cancel()
            try:
                await _task
            except asyncio.CancelledError:
                pass
    if paid_license_sync_task is not None:
        paid_license_sync_task.cancel()
        try:
            await paid_license_sync_task
        except asyncio.CancelledError:
            pass
    if oss_heartbeat_task is not None:
        oss_heartbeat_task.cancel()
        try:
            await oss_heartbeat_task
        except asyncio.CancelledError:
            pass

    try:
        _log_drain_task.cancel()
        await _log_drain_task
    except asyncio.CancelledError:
        pass
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
    await sip_server.stop()
    try:
        from app.services.zlm_rtp_server_service import close_shared_zlm_client
        await close_shared_zlm_client()
    except Exception as e:
        logger.warning(f"Close ZLM client failed: {e}")

_env = (getattr(settings, "APP_ENV", "dev") or "dev").lower()

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
except Exception:
    pass


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next) -> Response:
        response: Response = await call_next(request)
        if not bool(getattr(settings, "ENABLE_SECURITY_HEADERS", True)):
            return response

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        if bool(getattr(settings, "ENABLE_CROSS_ORIGIN_ISOLATION", False)):
            response.headers.setdefault(
                "Cross-Origin-Embedder-Policy",
                str(getattr(settings, "CROSS_ORIGIN_EMBEDDER_POLICY", "credentialless") or "credentialless"),
            )

        # HSTS only when behind HTTPS
        try:
            if str(getattr(request.url, "scheme", "")).lower() == "https":
                response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        except Exception as e:
            logger.warning(f"Error: {e}")

        if bool(getattr(settings, "ENABLE_CSP", False)):
            # NOTE: CSP currently uses unsafe-inline/unsafe-eval for compatibility with
            # OpenLayers map library and Jessibuca/H265 video players.
            # TODO: Migrate to nonce-based CSP once player components support it.
            #   1. Generate a random nonce per request: nonce = secrets.token_urlsafe(16)
            #   2. Set script-src to 'self' 'nonce-{nonce}' (remove unsafe-inline/unsafe-eval)
            #   3. Pass nonce to frontend templates via header or meta tag
            #   4. Update Jessibuca/OpenLayers script tags to include nonce attribute
            # Production deployments should use a reverse proxy (Nginx) with stricter CSP.
            # Keep CSP permissive-by-default to avoid breaking maps/players.
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; "
                "base-uri 'self'; "
                "frame-ancestors 'none'; "
                "img-src 'self' data: blob: tile: https://t?.tianditu.gov.cn https://web?.is.autonavi.com https://maponline?.bdimg.com https://*.arcgisonline.com; "
                "media-src 'self' data: blob:; "
                "connect-src 'self' http: https: ws: wss:; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'",
            )

        return response


app.add_middleware(SecurityHeadersMiddleware)

# Production safety checks: refuse known default secrets
# Note: config.py 中已有先序检查（SystemExit），此处为兜底防护（RuntimeError）
import hashlib as _hashlib
import os as _os

# Common weak passwords list
_DEFAULT_PASSWORDS = {
    "password", "12345678", "admin", "root", "administrator",
    "123456", "123456789", "1234567890", "admin123", "admin1234",
    "Abc12345", "Passw0rd", "Passw0rd!", "rootroot", "testtest",
}

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
    return False

if (getattr(settings, "APP_ENV", "dev") or "dev").lower() in {"prod", "production"}:
    if _is_weak_secret(settings.SECRET_KEY):
        raise RuntimeError("SECURITY: SECRET_KEY is empty, too short, or using a weak/default value. Please set a strong SECRET_KEY (32+ chars) via environment variable in production.")
    if _is_weak_secret(getattr(settings, "MEDIA_SERVER_SECRET", "")):
        raise RuntimeError("SECURITY: MEDIA_SERVER_SECRET is empty, too short, or using a weak/default value. Please set a strong MEDIA_SERVER_SECRET via environment variable in production.")
    _db_type = (getattr(settings, "DATABASE_TYPE", "") or "").lower()
    if _db_type not in {"sqlite"}:
        for _pwd_key in ["POSTGRES_PASSWORD", "DATABASE_PASSWORD"]:
            _pwd_val = str(getattr(settings, _pwd_key, "") or "").strip().lower()
            if _pwd_val in _DEFAULT_PASSWORDS or _pwd_val == "":
                raise RuntimeError(f"SECURITY: {_pwd_key} is using a default or empty password. Please set a strong password in production.")
    _sip_pwd = str(getattr(settings, "SIP_DEFAULT_PASSWORD", "") or "").strip().lower()
    if _sip_pwd in _DEFAULT_PASSWORDS or _sip_pwd == "":
        raise RuntimeError("SECURITY: SIP_DEFAULT_PASSWORD is using a default or empty password. Please set a strong password in production.")
    if bool(getattr(settings, "ALLOW_PUBLIC_REGISTRATION", False)):
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
    _cors_env = (getattr(settings, "APP_ENV", "dev") or "dev").lower()
    _cors_origins = [str(origin) for origin in settings.BACKEND_CORS_ORIGINS]
    if _cors_env in {"prod", "production"}:
        # Exact hostname matching to prevent bypass (e.g., "mylocalhost.com")
        from urllib.parse import urlparse as _urlparse
        for origin in _cors_origins:
            parsed = _urlparse(origin)
            hostname = (parsed.hostname or "").lower()
            if hostname in ("localhost", "127.0.0.1", "::1"):
                raise RuntimeError(f"SECURITY: BACKEND_CORS_ORIGINS contains '{origin}' with localhost/loopback address, which is not allowed in production.")
        # W-09 生产环境CORS禁止通配符*，防止跨域安全策略失效
        if any(o.strip() == "*" for o in _cors_origins):
            raise RuntimeError("SECURITY: BACKEND_CORS_ORIGINS must not contain wildcard '*' in production")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With", "X-API-Key", "X-Sensitive-Operation"],
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
    detail = exc.detail
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
    _env = (getattr(settings, "APP_ENV", "dev") or "dev").lower()
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

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
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
    """无鉴权健康检查，供负载均衡/容器探针使用。"""
    checks = {"status": "ok", "db": "ok"}
    try:
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        checks["status"] = "degraded"
        checks["db"] = f"error: {e}"
    # Check Redis: distinguish "not configured" vs "configured but unreachable"
    try:
        from app.core.redis import redis_client as _rc
        if _rc is not None:
            await _rc.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "not_configured"
    except Exception as e:
        checks["redis"] = f"error: {e}"
        if checks["status"] == "ok":
            checks["status"] = "degraded"
    status_code = 200 if checks["status"] == "ok" else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(content=checks, status_code=status_code)


@app.get("/health/ready")
@app.get("/api/v1/health/readiness")
async def health_ready():
    """Readiness probe: checks if the application is ready to accept traffic (DB + Redis must be up)."""
    checks = {"status": "ready", "db": "ok"}
    try:
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        checks["status"] = "not_ready"
        checks["db"] = f"error: {e}"
    try:
        from app.core.redis import redis_client as _rc
        if _rc is not None:
            await _rc.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "not_configured"
    except Exception as e:
        checks["redis"] = f"error: {e}"
        if checks["status"] == "ready":
            checks["status"] = "not_ready"
    status_code = 200 if checks["status"] == "ready" else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(content=checks, status_code=status_code)


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
    allowed_networks = getattr(settings, 'METRICS_ALLOWED_NETWORKS', ['127.0.0.1', '::1', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'])
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
    port = getattr(settings, "BACKEND_PUBLIC_PORT", 8000)
    # S-04 — 生产环境绑定 0.0.0.0 时发出警告，防止无意识暴露
    _host = "127.0.0.1"
    if _env in {"prod", "production"}:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "PRODUCTION: binding backend to 127.0.0.1 (not 0.0.0.0) for security. "
            "Use a reverse proxy (nginx) for external access."
        )
    else:
        _host = "0.0.0.0"
    uvicorn.run("app.main:app", host=_host, port=port, reload=_env == "dev", loop="asyncio", timeout_keep_alive=settings.UVICORN_TIMEOUT_KEEP_ALIVE)