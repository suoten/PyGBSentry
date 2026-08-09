"""行政区划导入服务。

从 ``data/region.sql`` 将内置行政区划导入到 ``regions`` 表。若 SQL 文件不存在
则写入一个最小根行政区划（使用 ``SIP_DOMAIN`` 作为编码），并提示运维人员后续
导入完整数据。

该模块对应启动流程中的 ``ensure_regions_seeded_from_sql`` 步骤，由
``app/core/startup.py`` 在 ``RUN_REGION_SEED_ON_STARTUP=true`` 时调用，
亦可被 ``scripts/seed_regions.py`` 单独调用。

幂等性：仅在 ``regions`` 表为空时执行导入，已存在数据则直接返回。任何异常均被
捕获并记录日志，绝不向上抛出（启动步骤不应因导入失败而中断）。
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.region import Region

# 行政区划 SQL 文件位置：backend/data/region.sql
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_REGION_SQL = _DATA_DIR / "region.sql"

# 旧 region 表 INSERT 行正则：INSERT INTO `region` VALUES ('1', '中国', '0', '1', '1', '0', '0');
# 列顺序：(id, name, pid, sort, level, longcode, code)
_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+`?region`?\s+VALUES\s*\(([^)]*)\)\s*;",
    re.IGNORECASE,
)


def _split_sql_values(values_blob: str) -> list[str]:
    """将 SQL VALUES 子句中的值列表拆分为单个字段字符串（去除引号）。"""
    items: list[str] = []
    for raw in values_blob.split(","):
        raw = raw.strip()
        if not raw:
            items.append("")
            continue
        if raw.startswith("'") and raw.endswith("'"):
            raw = raw[1:-1]
        items.append(raw.replace("\\'", "'").replace('""', '"'))
    return items


def _deterministic_id(longcode: str) -> str:
    """根据 longcode 生成确定性 UUID（保证重复导入得到相同 id）。"""
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"pygbsentry.region:{longcode}").hex


async def _count_regions(db: AsyncSession) -> int:
    cnt = await db.execute(select(func.count(Region.id)))
    return int(cnt.scalar() or 0)


def _parse_region_sql(sql_text: str) -> list[dict[str, Any]]:
    """解析 region.sql，返回按 (id 升序) 排序的字典列表。

    旧表列：id, name, pid, sort, level, longcode, code
    新表字段映射：code<-longcode, name<-name, level<-level-1, sort_order<-sort,
    parent_id 由 pid 经 longcode 映射得到。
    """
    rows: list[dict[str, Any]] = []
    for match in _INSERT_RE.finditer(sql_text):
        fields = _split_sql_values(match.group(1))
        if len(fields) < 7:
            continue
        old_id, name, pid, sort, level, longcode, _code = fields[:7]
        try:
            level_int = int(level or "0")
            sort_int = int(sort or "0")
        except ValueError:
            level_int = 0
            sort_int = 0
        rows.append(
            {
                "old_id": old_id,
                "name": name or "",
                "pid": pid or "0",
                "sort": sort_int,
                "level": max(0, level_int - 1),  # 旧 level 1→新 level 0（国家）
                "longcode": longcode or "",
            }
        )
    rows.sort(key=lambda r: int(r["old_id"]) if r["old_id"].isdigit() else 0)
    return rows


async def _seed_from_sql(db: AsyncSession, rows: list[dict[str, Any]]) -> int:
    """将解析后的行写入 regions 表。返回插入条数。"""
    # 建立 old_id -> new_id 映射，用于解析 parent_id
    id_map: dict[str, str] = {}
    for row in rows:
        id_map[row["old_id"]] = _deterministic_id(row["longcode"] or row["old_id"])

    inserted = 0
    for row in rows:
        longcode = row["longcode"] or ""
        if not longcode:
            continue
        new_id = id_map[row["old_id"]]
        pid = row["pid"] or "0"
        parent_id = id_map.get(pid) if pid and pid != "0" else None
        region = Region(
            id=new_id,
            code=longcode,
            name=row["name"],
            parent_id=parent_id,
            level=int(row["level"]),
            sort_order=int(row["sort"]),
        )
        db.add(region)
        inserted += 1
    if inserted:
        await db.commit()
    return inserted


async def _seed_minimal_root(db: AsyncSession) -> int:
    """SQL 文件缺失时写入最小根行政区划。"""
    root_code = str(settings.SIP_DOMAIN or "3402000000")
    if not re.match(r"^\d{10}$", root_code):
        root_code = "0000000000"
    existing = (
        await db.execute(select(Region).where(Region.code == root_code))
    ).scalars().first()
    if existing:
        return 0
    db.add(
        Region(
            id=_deterministic_id(root_code),
            code=root_code,
            name="根行政区划",
            parent_id=None,
            level=0,
            sort_order=0,
        )
    )
    await db.commit()
    logger.warning(
        "region.sql not found at {}; seeded minimal root region code={}. "
        "Operators should import the full region set via scripts/seed_regions.py.".format(
            _REGION_SQL, root_code
        )
    )
    return 1


async def ensure_regions_seeded_from_sql(db: AsyncSession) -> dict[str, Any]:
    """若 regions 表为空，从 data/region.sql 导入行政区划。

    幂等：表非空时直接返回 ``{"skipped": True, ...}``。
    永不抛异常：所有异常均被捕获并记录日志，返回 ``{"error": ...}``。
    """
    try:
        existing = await _count_regions(db)
        if existing > 0:
            return {"skipped": True, "existing": existing, "imported": 0}

        if _REGION_SQL.exists():
            try:
                sql_text = _REGION_SQL.read_text(encoding="utf-8", errors="ignore")
            except Exception as read_err:
                logger.warning("Failed to read region.sql: {}", read_err)
                n = await _seed_minimal_root(db)
                return {"imported": n, "source": "minimal_root", "existing": existing}
            rows = _parse_region_sql(sql_text)
            if not rows:
                logger.warning("region.sql parsed 0 rows; seeding minimal root.")
                n = await _seed_minimal_root(db)
                return {"imported": n, "source": "minimal_root", "existing": existing}
            n = await _seed_from_sql(db, rows)
            logger.info("ensure_regions_seeded_from_sql imported {} regions from {}", n, _REGION_SQL)
            return {"imported": n, "source": "region.sql", "existing": existing}

        n = await _seed_minimal_root(db)
        return {"imported": n, "source": "minimal_root", "existing": existing}
    except Exception as e:
        logger.warning("ensure_regions_seeded_from_sql failed (non-fatal): {}", e)
        try:
            await db.rollback()
        except Exception as _rb_err:
            # FIX [2026-07-17 P3-17]: 描述性日志替代 "silently_swallowed_exception"
            logger.warning(f"ensure_regions_seeded_from_sql: db.rollback also failed: {_rb_err}")
        return {"error": str(e), "imported": 0}
