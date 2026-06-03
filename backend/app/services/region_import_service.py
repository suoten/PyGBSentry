from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from fastapi import HTTPException
from loguru import logger
from sqlalchemy import select, func  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.region import Region, generate_uuid


_INSERT_RE = re.compile(r"INSERT INTO\s+`?region`?\s+VALUES\s*\((.+)\);", re.IGNORECASE)
_FIELD_RE = re.compile(r"'([^']*)'")


def _region_sql_path() -> Path:
    # .../backend/app/services -> .../backend/data/region.sql（随开源版内置）
    return Path(__file__).resolve().parents[2] / "data" / "region.sql"


def _parse_insert_fields(line: str) -> list[str] | None:
    m = _INSERT_RE.search(line)
    if not m:
        return None
    fields = _FIELD_RE.findall(m.group(1))
    if len(fields) < 7:
        return None
    return fields


async def ensure_regions_seeded_from_sql(db: AsyncSession) -> dict[str, Any]:
    count_stmt = select(func.count()).select_from(Region)
    existing_count = int((await db.execute(count_stmt)).scalar() or 0)
    if existing_count > 0:
        return {"seeded": False, "reason": "regions_not_empty", "rows": existing_count}

    sql_path = _region_sql_path()
    if not sql_path.exists():
        logger.warning("Region SQL not found: {}", sql_path)
        return {"seeded": False, "reason": "sql_not_found", "rows": 0}

    # 仅导入到“区县”层级：
    # 原始 level: 2省、3市、4区县（5/6为街道/社区，这里不导入）
    raw_rows: dict[str, dict[str, Any]] = {}
    try:
        with sql_path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                fields = _parse_insert_fields(line)
                if not fields:
                    continue
                source_id, name, pid, sort, src_level, longcode, _short_code = fields[:7]
                try:
                    src_level_i = int(src_level)
                except Exception:
                    continue
                if src_level_i < 2 or src_level_i > 4:
                    continue
                raw_rows[source_id] = {
                    "source_id": source_id,
                    "name": name.strip(),
                    "pid": pid.strip(),
                    "sort_order": int(sort or 0),
                    "src_level": src_level_i,
                    "code": longcode.strip(),
                }
    except (FileNotFoundError, UnicodeDecodeError) as e:
        logger.error(f"Region SQL import failed: {e}")
        raise HTTPException(status_code=500, detail="Region data import failed") from e  # 文件I/O异常保护

    if not raw_rows:
        return {"seeded": False, "reason": "no_rows_parsed", "rows": 0}

    # 先按层级创建，保证能回填 parent_id。
    # 使用显式 id，避免每行 await flush()（数千次往返会阻塞事件循环数分钟，导致 HTTP 端口迟迟不监听）。
    source_to_region_id: dict[str, str] = {}
    created = 0
    for src_level in (2, 3, 4):
        for row in (r for r in raw_rows.values() if r["src_level"] == src_level):
            parent_id = None
            if src_level > 2:
                parent_source_id = row["pid"]
                parent_id = source_to_region_id.get(parent_source_id)
                if not parent_id:
                    continue

            rid = generate_uuid()
            region = Region(
                id=rid,
                code=row["code"],
                name=row["name"] or row["code"],
                parent_id=parent_id,
                level=src_level - 2,  # 0=省, 1=市, 2=区县
                sort_order=row["sort_order"],
            )
            db.add(region)
            source_to_region_id[row["source_id"]] = rid
            created += 1
        await db.flush()

    await db.commit()
    logger.info("Seeded regions from SQL: {} rows", created)
    return {"seeded": True, "reason": "ok", "rows": created}
