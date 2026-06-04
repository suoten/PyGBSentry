from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event
from app.core.config import settings
import sqlite3
import shutil
import os
import re
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
    _sqlite_timeout = float(getattr(settings, "SQLITE_CONNECT_TIMEOUT_SECONDS", 15.0) or 15.0)
    engine_kwargs["connect_args"] = {"timeout": _sqlite_timeout}
    engine_kwargs["pool_size"] = int(getattr(settings, "SQLITE_POOL_SIZE", 20) or 20)
    engine_kwargs["max_overflow"] = int(getattr(settings, "SQLITE_MAX_OVERFLOW", 30) or 30)
else:
    engine_kwargs.update(
        {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_recycle": settings.DB_POOL_RECYCLE,
        }
    )
    # FIXED-P0: asyncpg 与 aware datetime 不兼容的统一解决方案
    # PostgreSQL 的 TIMESTAMP WITHOUT TIME ZONE 列不接受带时区的 datetime 参数，
    # 但代码中有 247 处使用 datetime.now(timezone.utc) 产生 aware datetime。
    # asyncpg 在内部类型检查时会将 aware datetime 与 naive datetime 做减法比较，
    # 导致 "can't subtract offset-naive and offset-aware datetimes" 错误。
    # set_type_codec 无法解决此问题，因为类型检查在编码器之前执行。
    # 解决方案：通过 SQLAlchemy 的 before_execute 事件，在参数传递给 asyncpg 之前，
    # 自动将所有 aware datetime 转为 naive datetime。
    async def _asyncpg_init_connection(conn):
        return conn

    engine_kwargs["connect_args"] = {
        "init": _asyncpg_init_connection,
        "statement_cache_size": 0,
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
    return statement, parameters

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

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise