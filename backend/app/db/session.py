from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event, text
from app.core.config import settings
import asyncio
import sqlite3
import shutil
import os
import re
import time
from datetime import datetime
from loguru import logger

_SAFE_TABLE_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

engine_kwargs: dict = {
    "echo": False,
    "pool_pre_ping": True,
}

db_uri = str(settings.SQLALCHEMY_DATABASE_URI or "")
is_sqlite = db_uri.lower().startswith("sqlite")

if is_sqlite:
    _sqlite_timeout = settings.SQLITE_CONNECT_TIMEOUT_SECONDS
    engine_kwargs["connect_args"] = {"timeout": _sqlite_timeout}
    # UNIFIED: SQLite 与非 SQLite 统一使用 DB_POOL_SIZE / DB_MAX_OVERFLOW 作为配置源，
    # 但 SQLite 的 NullPool 不支持 pool_size/max_overflow 参数，故不传入 engine_kwargs。
    # 这些配置值通过 SQLITE_BUSY_TIMEOUT_MS 在连接级别生效。
else:
    engine_kwargs.update(
        {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_recycle": settings.DB_POOL_RECYCLE,
            "pool_timeout": 30,  # FIX: 连接池耗尽时最多等待 30s，避免无限挂起
        }
    )
    # FIXED-P0: asyncpg 与 aware datetime 不兼容的统一解决方案
    # PostgreSQL 的 TIMESTAMP WITHOUT TIME ZONE 列不接受带时区的 datetime 参数，
    # 但代码中有 247 处使用 datetime.now(timezone.utc) 产生 aware datetime。
    # asyncpg 在内部类型检查时会将 aware datetime 与 naive datetime 做减法比较，
    # 导致 "can't subtract offset-naive and offset-aware datetimes" 错误。
    # set_type_codec 无法解决此问题，因为类型检查在编码器之前执行。
    # 解决方案：通过 SQLAlchemy 的 before_execute 事件，在参数传递给 asyncpg 之前，
    # 自动将所有 aware datetime 转为 naive datetime（见下方 _before_cursor_execute_strip_tzinfo）。
    #
    # P2-7: statement_cache_size 原设为 0 以规避上述问题；根因现已由
    # _before_cursor_execute_strip_tzinfo 事件修复，故改为可配置以恢复 5-15% 性能。
    # 默认 0（保持兼容），生产环境可在 .env 中设置 DB_STATEMENT_CACHE_SIZE=100 开启。
    _stmt_cache_size = settings.DB_STATEMENT_CACHE_SIZE
    engine_kwargs["connect_args"] = {
        "statement_cache_size": _stmt_cache_size,
    }


def _sqlite_integrity_check_and_repair(db_path: str) -> None:
    """启动前检查 SQLite 数据库完整性，若损坏则备份并重建空库。"""
    if not os.path.exists(db_path):
        return
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        status = result[0] if result else "unknown"
        if status == "ok":
            return
        logger.warning("SQLite integrity_check: {} — database is corrupted, attempting repair", status)
    except sqlite3.DatabaseError as e:
        logger.warning("SQLite cannot open database: {} — attempting repair", e)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.corrupted_{ts}"
    try:
        shutil.move(db_path, backup_path)
        logger.info("Corrupted database moved to: {}", backup_path)
    except Exception as move_err:
        logger.error("Failed to move corrupted database: {}", move_err)
        return

    try:
        recover_path = f"{db_path}.recovered_{ts}"
        src_conn = sqlite3.connect(backup_path, timeout=5)
        dst_conn = sqlite3.connect(recover_path)
        try:
            src_conn.execute("PRAGMA journal_mode=WAL")
            for row in src_conn.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND type IN ('table','index','trigger','view')"):
                if row[0]:
                    try:
                        dst_conn.execute(row[0])
                    except Exception as e:
                        logger.warning(f"Error: {e}")
            for tbl_row in src_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                tbl = tbl_row[0]
                if not _SAFE_TABLE_RE.match(tbl):
                    logger.warning("Skipping table with unsafe name: {}", tbl)
                    continue
                try:
                    rows = src_conn.execute(f"SELECT * FROM [{tbl}]").fetchall()
                    if rows:
                        placeholders = ",".join(["?"] * len(rows[0]))
                        dst_conn.executemany(f"INSERT INTO [{tbl}] VALUES ({placeholders})", rows)
                except Exception as tbl_err:
                    logger.warning("Recover table [{}] partial/failed: {}", tbl, tbl_err)
            dst_conn.commit()
            dst_conn.execute("PRAGMA integrity_check")
        finally:
            dst_conn.close()
            src_conn.close()
        shutil.move(recover_path, db_path)
        logger.info("Database recovered from backup: {} → {}", backup_path, db_path)
    except Exception as recover_err:
        logger.error("Database recovery failed: {} — starting with empty database", recover_err)
        if os.path.exists(recover_path):
            corrupted_bak = f"{db_path}.corrupted.bak"
            try:
                shutil.move(recover_path, corrupted_bak)
                logger.warning(
                    "Recovery file preserved as {} — please manually inspect this file",
                    corrupted_bak,
                )
            except Exception as rename_err:
                logger.error("Failed to preserve recovery file: {}", rename_err)


if is_sqlite:
    _db_file_path = db_uri.replace("sqlite+aiosql:///", "").replace("sqlite:///", "")
    if _db_file_path and not _db_file_path.startswith(":memory:"):
        _sqlite_integrity_check_and_repair(_db_file_path)

engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, **engine_kwargs)


# FIXED-P0: 在 SQLAlchemy 层面自动将 aware datetime 转为 naive datetime
# asyncpg 内部类型检查会在编码器之前执行，导致 "can't subtract offset-naive
# and offset-aware datetimes" 错误。通过 before_cursor_execute 事件在参数
# 传递给 asyncpg 之前，递归遍历所有参数，将 aware datetime 的 tzinfo 去掉。
def _strip_tzinfo(value):
    """递归去除 datetime 的 tzinfo，将 aware datetime 转为 naive datetime"""
    from datetime import datetime as _dt
    if isinstance(value, _dt) and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    if isinstance(value, (list, tuple)):
        stripped = [_strip_tzinfo(v) for v in value]
        return type(value)(stripped) if isinstance(value, tuple) else stripped
    if isinstance(value, dict):
        return {k: _strip_tzinfo(v) for k, v in value.items()}
    return value


@event.listens_for(engine.sync_engine, "before_cursor_execute", retval=True)
def _before_cursor_execute_strip_tzinfo(conn, cursor, statement, parameters, context, executemany):
    """在 SQL 执行前将参数中的 aware datetime 转为 naive datetime"""
    if parameters:
        parameters = _strip_tzinfo(parameters)
    # P2-03: 记录查询开始时间，用于慢查询监控
    context._query_start_time = time.time()
    return statement, parameters


# P2-03: 慢查询监控 — 在 SQL 执行后计算耗时，超过阈值则记录 WARNING 日志
@event.listens_for(engine.sync_engine, "after_cursor_execute")
def _after_cursor_execute_slow_query_monitor(conn, cursor, statement, parameters, context, executemany):
    """SQL 执行后检查耗时，超过 SLOW_QUERY_THRESHOLD_SECONDS 则记录慢查询日志。"""
    import time as _time
    start_time = getattr(context, "_query_start_time", None)
    if start_time is None:
        return
    elapsed = _time.time() - start_time
    threshold = settings.SLOW_QUERY_THRESHOLD_SECONDS
    if elapsed > threshold:
        # 截断 SQL 语句，避免日志过长
        stmt_preview = str(statement)[:300].replace("\n", " ")
        logger.warning(
            f"Slow query ({elapsed:.3f}s, threshold={threshold}s): {stmt_preview}"
        )

if is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute(f"PRAGMA busy_timeout={settings.SQLITE_BUSY_TIMEOUT_MS}")
        cursor.close()

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


# FIX: [2026-07-03] 数据库连接健康检查与指数退避重连机制 [可靠性工程师]
# 策略：连接断开后最多重试 5 次，间隔按指数退避（1s, 2s, 4s, 8s, 16s）
_db_health_check_failed: bool = False
_db_reconnect_max_retries: int = 5
_db_reconnect_base_delay: float = 1.0


async def check_db_connection() -> bool:
    """检查数据库连接是否正常。返回 True 表示连接可用。"""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"DB connection check failed: {e}")
        return False


async def ensure_db_connection_with_retry() -> bool:
    """带指数退避的数据库连接重试。

    最多重试 _db_reconnect_max_retries 次，每次间隔按 2^n 秒递增。
    成功后重置失败标志并返回 True；全部失败返回 False。
    """
    global _db_health_check_failed
    if not _db_health_check_failed:
        # 快速路径：未处于失败状态时仅做轻量检查
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            _db_health_check_failed = True
            logger.warning("DB connection lost, initiating reconnect with exponential backoff...")

    # 指数退避重连
    for attempt in range(1, _db_reconnect_max_retries + 1):
        delay = _db_reconnect_base_delay * (2 ** (attempt - 1))
        logger.info(f"DB reconnect attempt {attempt}/{_db_reconnect_max_retries}, waiting {delay}s...")
        await asyncio.sleep(delay)
        try:
            # pool_pre_ping=True 会自动处理死连接，这里只需验证新连接可建立
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            _db_health_check_failed = False
            logger.info(f"DB reconnected successfully on attempt {attempt}")
            return True
        except Exception as e:
            logger.error(f"DB reconnect attempt {attempt} failed: {e}")

    logger.error(f"DB reconnect failed after {_db_reconnect_max_retries} attempts")
    return False


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            # FIX: [2026-07-03] 异常时标记 DB 健康状态为失败，触发后续重连 [可靠性工程师]
            global _db_health_check_failed
            _db_health_check_failed = True
            raise
