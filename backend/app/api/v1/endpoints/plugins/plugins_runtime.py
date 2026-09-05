"""
plugins_runtime — 插件运行时配置相关端点。
"""

import re
import asyncio
import csv
import io
import json
import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path as FSPath
from loguru import logger

from app.core.http_client import get_http_client
from fastapi import Query, APIRouter, UploadFile, File, HTTPException, Depends, Request, Form
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select, MetaData, Table, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.models.user import User
from app.models.system_setting import SystemSetting
from app.models.resource import Resource
from app.db.session import get_db, engine
from app.core.plugin_manager import plugin_manager
from app.core.config import settings
from app.services.audit_center_service import audit_center_service
from app.services.auth_audit import safe_auth_audit
from app.core.zlm_target import resolve_zlm_api_target
from .plugins_market import list_purchased_plugins_proxy

from .plugins_common import (
    _validate_plugin_asset_id,
    _plugin_dir_abs,
    _ensure_loaded_plugin,
    _safe_join_asset,
    _audit_tid,
    _parse_face_db_identities,
    _load_face_db_raw,
    _face_db_path_abs,
    _read_marketplace_catalog,
    _read_plugin_tables,
    _version_lt,
    require_oss_paid_runtime_from_path,
    _STREAM_HEALTH_CACHE_LOCK,
    _STREAM_HEALTH_CACHE_TS,
    _STREAM_HEALTH_CACHE_RAW,
    PLUGIN_DIR_ABS,
    PluginTableQueryRequest,
    PluginTableExportRequest,
    PluginRuntimeConfigUpdate,
    FaceDbDeleteRequest,
)

router = APIRouter()


@router.get("/plugin-assets/{plugin_id}/{asset_path:path}")
async def plugin_assets(
    plugin_id: str,
    asset_path: str = "index.html",
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    OSS 端插件运行页使用 iframe 加载 /plugin-assets/{plugin_id}/index.html。
    这里从安装目录 plugins/{plugin_id}/ 读取静态资源（同时兼容常见 dist/www/frontend 子目录）。
    """
    pid = _validate_plugin_asset_id(plugin_id)

    # 常见前端打包输出目录优先级
    roots = [
        PLUGIN_DIR_ABS,
        PLUGIN_DIR_ABS / pid / "dist",
        PLUGIN_DIR_ABS / pid / "www",
        PLUGIN_DIR_ABS / pid / "frontend",
    ]

    def _safe_join_generic(root_dir: FSPath, ap: str) -> FSPath:
        ap2 = (ap or "").lstrip("/").replace("\\", "/")
        if not ap2:
            ap2 = "index.html"
        if ".." in ap2.split("/"):
            raise HTTPException(status_code=400, detail="invalid asset path")
        return (root_dir / ap2).resolve()

    # 对每个 root 都尝试匹配 asset_path
    for r in roots:
        try:
            if r == PLUGIN_DIR_ABS:
                # 直接从 plugins/{plugin_id}/{asset_path}
                target = _safe_join_asset(PLUGIN_DIR_ABS, pid, asset_path)
            else:
                # 从 dist/www/frontend 下读取
                target = _safe_join_generic(r, asset_path or "index.html")
            if target.exists() and target.is_file():
                return FileResponse(str(target))
            str(target)
        except HTTPException:
            # 参数非法直接抛
            raise
        except Exception:
            continue

    raise HTTPException(status_code=404, detail="plugin asset not found")


@router.get("/installed")
async def list_installed_plugins(
    current_user: User = Depends(deps.get_current_active_user),
):
    marketplace_items = _read_marketplace_catalog()
    marketplace_by_id: dict[str, dict] = {}
    for it in marketplace_items:
        if not isinstance(it, dict):
            continue
        pid = str(it.get("id") or it.get("plugin_id") or "").strip()
        if pid:
            marketplace_by_id[pid] = it

    result = []
    for plugin_id in plugin_manager.plugins.keys():
        meta = plugin_manager.metadata.get(plugin_id, {}) or {}
        mp_item = marketplace_by_id.get(str(plugin_id), {})

        display_name = (
            meta.get("name")
            or meta.get("title")
            or (mp_item.get("name") if isinstance(mp_item, dict) else None)
            or (mp_item.get("title") if isinstance(mp_item, dict) else None)
            or plugin_id
        )

        ptype = meta.get("type") or (mp_item.get("type") if isinstance(mp_item, dict) else None) or "free"
        version = meta.get("version") or (mp_item.get("version") if isinstance(mp_item, dict) else None) or "0.0.0"
        has_menu = isinstance(meta.get("menu"), (dict, list)) or isinstance(mp_item.get("menu"), (dict, list))

        result.append({
            "id": plugin_id,
            "name": display_name,
            "version": version,
            "type": ptype,
            "has_menu": has_menu,
        })

    return result


@router.get("/menus")
async def list_plugin_menus(
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
):
    from .plugins_common import (
        _build_menu_entries,
    )
    import time

    _PLUGIN_MENU_CACHE_TTL = 60

    if (settings.APP_EDITION or "oss").lower() == "server":
        return _build_menu_entries()

    now_mono = time.monotonic()
    pm = plugin_manager
    if pm._plugin_menu_cache and (now_mono - pm._plugin_menu_cache_ts) < _PLUGIN_MENU_CACHE_TTL:
        return pm._plugin_menu_cache.get("entries", [])

    eligible_ids = await pm._compute_eligible_plugin_ids()

    if getattr(current_user, "is_superuser", False):
        purchased_ids: set[str] | None = None
    else:
        purchased = await list_purchased_plugins_proxy(request, current_user)
        purchased_ids = {str(pid) for pid in (purchased.get("plugin_ids") or [])}

    if eligible_ids and purchased_ids is not None:
        purchased_ids = purchased_ids | eligible_ids
    elif eligible_ids:
        purchased_ids = eligible_ids
    # 先用"插件 metadata 声明的 menu"生成（适用于有 plugin.json/menu 的插件）
    entries = _build_menu_entries(purchased_ids)
    covered_plugin_ids = {str(e.get("plugin_id") or "") for e in entries if isinstance(e, dict)}

    # 再补齐：对 OSS 端已安装但缺少 plugin.json/menu metadata 的插件（通常是单文件插件）
    # 这类插件依然希望出现在侧栏，至少能进入 PluginRuntime 页面查看/配置（后端能力为主时无 iframe）。
    installed_ids = {str(pid) for pid in (plugin_manager.plugins.keys() or []) if pid}
    marketplace_items = _read_marketplace_catalog()
    marketplace_by_id: dict[str, dict] = {}
    for it in marketplace_items:
        if not isinstance(it, dict):
            continue
        pid = str(it.get("id") or it.get("plugin_id") or "").strip()
        if pid:
            marketplace_by_id[pid] = it

    for pid in sorted(installed_ids):
        if pid in covered_plugin_ids:
            continue
        mp_item = marketplace_by_id.get(pid) or {}
        ptype = str(mp_item.get("type") or "free").lower()
        if ptype == "paid" and purchased_ids is not None and pid not in purchased_ids:
            continue

        title = (
            (mp_item.get("menu", {}).get("title") if isinstance(mp_item.get("menu"), dict) else None)
            or mp_item.get("name")
            or mp_item.get("title")
            or pid
        )
        path = (
            (mp_item.get("menu", {}).get("path") if isinstance(mp_item.get("menu"), dict) else None)
            or f"/plugins/runtime/{pid}"
        )
        frontend_url = (
            (mp_item.get("menu", {}).get("frontend_url") if isinstance(mp_item.get("menu"), dict) else None)
            or (mp_item.get("frontend_url") if isinstance(mp_item.get("frontend_url"), str) else None)
            or None
        )

        entries.append({
            "plugin_id": pid,
            "title": title,
            "path": path,
            "frontend_url": frontend_url,
        })

    pm._plugin_menu_cache = {"entries": entries}
    pm._plugin_menu_cache_ts = time.monotonic()

    return entries


@router.get("/mobile-entries")
async def list_mobile_plugin_entries(
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
) -> dict:
    """
    列出当前已加载插件中，声明了移动端 / 小程序入口的插件。

    用途：
    - 手机 App / 小程序统一拉取"可在移动端使用的插件列表"
    - 不直接注入 token，仅透出 entry_url / entry_url_template，由前端或网关按需拼接
    - 付费插件与 PC 侧栏一致：仅当已购买（或免费）才透出
    """
    from .plugins_common import (
        MobilePluginEntry,
    )

    if getattr(current_user, "is_superuser", False):
        purchased_ids: set[str] | None = None
    else:
        purchased = await list_purchased_plugins_proxy(request, current_user)
        purchased_ids = {str(pid) for pid in (purchased.get("plugin_ids") or [])}

    items: list[MobilePluginEntry] = []
    for plugin_id, meta in plugin_manager.metadata.items():
        if not isinstance(meta, dict):
            continue
        ptype = str(meta.get("type") or "").lower()
        if ptype == "paid" and purchased_ids is not None and plugin_id not in purchased_ids:
            continue
        name = str(meta.get("name") or meta.get("title") or plugin_id)
        platforms = meta.get("platforms")
        normalized_platforms: set[str] = set()
        if isinstance(platforms, list):
            for p in platforms:
                if isinstance(p, str) and p.strip():
                    normalized_platforms.add(p.strip().lower())
        if not normalized_platforms:
            normalized_platforms = {"pc"}

        for key, platform_name in (("mobile", "mobile"), ("miniprogram", "miniprogram")):
            if platform_name not in normalized_platforms:
                continue
            raw = meta.get(key)
            if not isinstance(raw, dict):
                continue
            entry_type = str(raw.get("entry_type") or "none").lower()
            if entry_type not in {"h5", "webview", "plugin", "native", "none"}:
                # 忽略非法声明，避免接口报错
                continue
            entry_url = raw.get("entry_url")
            entry_url_tmpl = raw.get("entry_url_template")
            items.append(
                MobilePluginEntry(
                    plugin_id=plugin_id,
                    name=name,
                    platform=platform_name,  # type: ignore[arg-type]
                    entry_type=entry_type,   # type: ignore[arg-type]
                    entry_url=str(entry_url) if isinstance(entry_url, str) and entry_url else None,
                    entry_url_template=str(entry_url_tmpl) if isinstance(entry_url_tmpl, str) and entry_url_tmpl else None,
                )
            )

    return {"items": items}


@router.get("/runtime/{plugin_id}/tables")
async def list_plugin_tables(
    plugin_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """列出某插件声明的 tables（用于方案2页面查询展示）。"""
    pid = str(plugin_id or "").strip()
    if not pid or pid not in plugin_manager.metadata:
        raise HTTPException(status_code=404, detail="Plugin not found or not loaded")
    tables = _read_plugin_tables(pid)
    return {"plugin_id": pid, "tables": tables}


@router.post("/runtime/{plugin_id}/tables/{table_name}/query")
async def query_plugin_table(
    plugin_id: str,
    table_name: str,
    payload: PluginTableQueryRequest,
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    通用查询接口（方案2）：
    - 只允许查询 plugin.json.tables 声明的表
    - 支持 where_eq / where_gte / where_lte（仅允许真实列名）
    - 支持 limit/offset/order_by
    """
    pid = str(plugin_id or "").strip()
    if not pid or pid not in plugin_manager.metadata:
        raise HTTPException(status_code=404, detail="Plugin not found or not loaded")

    declared = set(_read_plugin_tables(pid))
    tname = str(table_name or "").strip()
    if not tname or tname not in declared:
        raise HTTPException(status_code=403, detail="Table not declared in plugin tables")

    limit = int(payload.limit or 0)
    offset = int(payload.offset or 0)
    if limit <= 0:
        limit = 50
    if limit > 500:
        limit = 500
    if offset < 0:
        offset = 0

    tbl = await _reflect_table(tname)
    if tbl is None:
        raise HTTPException(status_code=404, detail="Table not found or cannot reflect")

    stmt = select(tbl)

    # where_eq: 仅允许列名存在且做等值过滤
    conds = []
    if isinstance(payload.where_eq, dict):
        for k, v in payload.where_eq.items():
            col = tbl.columns.get(str(k))
            if col is None:
                continue
            conds.append(col == v)

    def _maybe_parse_dt(col, raw_v):
        if not isinstance(raw_v, str):
            return raw_v
        try:
            py_t = getattr(getattr(col, "type", None), "python_type", None)
            if py_t is not datetime:
                return raw_v
            s = raw_v.strip()
            # handle trailing Z
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return datetime.fromisoformat(s)
        except Exception:
            return raw_v

    if isinstance(payload.where_gte, dict):
        for k, v in payload.where_gte.items():
            col = tbl.columns.get(str(k))
            if col is None:
                continue
            conds.append(col >= _maybe_parse_dt(col, v))
    if isinstance(payload.where_lte, dict):
        for k, v in payload.where_lte.items():
            col = tbl.columns.get(str(k))
            if col is None:
                continue
            conds.append(col <= _maybe_parse_dt(col, v))
    if conds:
        stmt = stmt.where(and_(*conds))

    # order_by: 仅允许真实列名
    if payload.order_by:
        col = tbl.columns.get(str(payload.order_by))
        if col is not None:
            stmt = stmt.order_by(col.desc() if payload.desc else col.asc())

    stmt = stmt.limit(limit).offset(offset)

    async with engine.connect() as conn:
        try:
            result = await conn.execute(stmt)
            rows = [dict(r._mapping) for r in result.fetchall()]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Query failed: {e}")

    return {
        "plugin_id": pid,
        "table": tname,
        "limit": limit,
        "offset": offset,
        "items": rows,
    }


@router.post("/runtime/{plugin_id}/tables/{table_name}/export")
async def export_plugin_table_csv(
    plugin_id: str,
    table_name: str,
    payload: PluginTableExportRequest,
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    通用 CSV 导出（方案2工作台用）：
    - 只允许导出 plugin.json.tables 声明的表
    - 支持 where_eq / where_gte / where_lte / order_by
    - 支持 columns 白名单（仅真实列名）
    """
    pid = str(plugin_id or "").strip()
    if not pid or pid not in plugin_manager.metadata:
        raise HTTPException(status_code=404, detail="Plugin not found or not loaded")

    declared = set(_read_plugin_tables(pid))
    tname = str(table_name or "").strip()
    if not tname or tname not in declared:
        raise HTTPException(status_code=403, detail="Table not declared in plugin tables")

    tbl = await _reflect_table(tname)
    if tbl is None:
        raise HTTPException(status_code=404, detail="Table not found or cannot reflect")

    # columns: only allow real column names
    all_cols = list(tbl.columns.keys())
    if payload.columns:
        cols = [c for c in payload.columns if isinstance(c, str) and c in tbl.columns]
        if not cols:
            cols = all_cols
    else:
        cols = all_cols

    stmt = select(*[tbl.columns[c] for c in cols])

    conds = []
    if isinstance(payload.where_eq, dict):
        for k, v in payload.where_eq.items():
            col = tbl.columns.get(str(k))
            if col is None:
                continue
            conds.append(col == v)

    def _maybe_parse_dt(col, raw_v):
        if not isinstance(raw_v, str):
            return raw_v
        try:
            py_t = getattr(getattr(col, "type", None), "python_type", None)
            if py_t is not datetime:
                return raw_v
            s = raw_v.strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return datetime.fromisoformat(s)
        except Exception:
            return raw_v

    if isinstance(payload.where_gte, dict):
        for k, v in payload.where_gte.items():
            col = tbl.columns.get(str(k))
            if col is None:
                continue
            conds.append(col >= _maybe_parse_dt(col, v))
    if isinstance(payload.where_lte, dict):
        for k, v in payload.where_lte.items():
            col = tbl.columns.get(str(k))
            if col is None:
                continue
            conds.append(col <= _maybe_parse_dt(col, v))
    if conds:
        stmt = stmt.where(and_(*conds))

    if payload.order_by:
        col = tbl.columns.get(str(payload.order_by))
        if col is not None:
            stmt = stmt.order_by(col.desc() if payload.desc else col.asc())

    max_rows = int(payload.max_rows or 0)
    if max_rows <= 0:
        max_rows = 100000
    if max_rows > 200000:
        max_rows = 200000
    stmt = stmt.limit(max_rows).offset(max(0, int(payload.offset or 0)))

    async with engine.connect() as conn:
        try:
            result = await conn.execute(stmt)
            rows = result.fetchall()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Export query failed: {e}")  # i18n

    def _iter_csv():
        # UTF-8 BOM for Excel
        yield "\ufeff"
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(cols)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        for r in rows:
            m = r._mapping
            writer.writerow([m.get(c) for c in cols])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    filename = f"{pid}_{tname}.csv"
    return StreamingResponse(
        _iter_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _reflect_table(table_name: str) -> Table | None:
    """
    运行时反射表结构（只用于插件自建表的通用查询）。
    不做 DDL，仅用于安全地拼装 SELECT。
    """
    tname = str(table_name or "").strip()
    if not tname:
        return None
    md = MetaData()

    async with engine.connect() as conn:
        def _load(sync_conn):
            return Table(tname, md, autoload_with=sync_conn)

        try:
            tbl: Table = await conn.run_sync(_load)
            return tbl
        except Exception as e:
            # FIX [2026-07-19 P1]: 原 except 静默 return None，表反射失败无法诊断。
            from loguru import logger
            logger.warning(f"_reflect_table failed table={tname}: {e}")
            return None


# ---------------------------------------------------------------------------
# Face DB endpoints
# ---------------------------------------------------------------------------

@router.get("/runtime/face_recognition_suite/face-db/meta")
async def face_db_meta(
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    人脸库元信息：用于插件页面展示当前库是否存在、人数等。
    文件位置固定在插件目录内：plugins/face_recognition_suite/face_db/identities.json
    """
    _ensure_loaded_plugin("face_recognition_suite")
    base = _plugin_dir_abs("face_recognition_suite")
    path = (base / "face_db" / "identities.json").resolve()
    if not str(path).startswith(str(base)):
        raise HTTPException(status_code=400, detail="invalid path")
    if not path.exists():
        return {"exists": False, "path": "face_db/identities.json", "count": 0}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        ids = _parse_face_db_identities(raw)
        return {"exists": True, "path": "face_db/identities.json", "count": len(ids)}
    except HTTPException:
        raise
    except Exception as e:
        return {"exists": True, "path": "face_db/identities.json", "count": 0, "error": str(e)}


@router.get("/runtime/face_recognition_suite/face-db/download")
async def face_db_download(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """下载当前人脸库 identities.json（若不存在返回 404）。"""
    _ensure_loaded_plugin("face_recognition_suite")
    base = _plugin_dir_abs("face_recognition_suite")
    path = (base / "face_db" / "identities.json").resolve()
    if not str(path).startswith(str(base)):
        raise HTTPException(status_code=400, detail="invalid path")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Face database not found")
    try:
        await audit_center_service.log(
            db=db,
            module="plugins",
            action="face_db_download",
            operator=current_user.username or "unknown",
            result="success",
            summary="plugin_id=face_recognition_suite; file=face_db/identities.json",
        )
    except Exception as e:
        logger.warning(f"Error: {e}")
    return FileResponse(str(path), media_type="application/json", filename="identities.json")


@router.post("/runtime/face_recognition_suite/face-db/upload")
async def face_db_upload(
    file: UploadFile = File(...),
    force: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    上传人脸库 identities.json。
    - 需要超级管理员（避免普通用户覆盖识别库）
    - 默认会校验 JSON 格式；force=true 时允许覆盖但仍会尽量 parse
    """
    _ensure_loaded_plugin("face_recognition_suite")
    if not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Only .json is supported")
    # FIX: [2026-07-16 P1] 限制 JSON 大小（5MB），防止 OOM
    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 5MB)")
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        raw = json.loads(content.decode("utf-8"))
        ids = _parse_face_db_identities(raw)
        if (not ids) and (not force):
            raise HTTPException(status_code=400, detail="Face database empty or no valid embeddings (use force=true to force overwrite)")  # i18n
    except HTTPException:
        raise
    except Exception as e:
        if not force:
            raise HTTPException(status_code=400, detail=f"JSON parse failed: {e}")
        raw = {"identities": []}
        ids = []

    base = _plugin_dir_abs("face_recognition_suite")
    db_dir = (base / "face_db").resolve()
    if not str(db_dir).startswith(str(base)):
        raise HTTPException(status_code=400, detail="invalid path")
    os.makedirs(str(db_dir), exist_ok=True)
    target = (db_dir / "identities.json").resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(status_code=400, detail="invalid path")
    # 防止磁盘满/权限不足时500无提示
    try:
        with open(target, "wb") as f:
            f.write(content)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Face database file write failed: {e}")  # i18n

    try:
        await audit_center_service.log(
            db=db,
            module="plugins",
            action="face_db_upload",
            operator=current_user.username or "unknown",
            result="success",
            summary=f"plugin_id=face_recognition_suite; file=face_db/identities.json; count={len(ids)}; force={bool(force)}",
        )
    except Exception as e:
        logger.warning(f"Error: {e}")

    return {"status": "ok", "saved": "face_db/identities.json", "count": len(ids)}


@router.get("/runtime/face_recognition_suite/face-db/list")
async def face_db_list(
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """列出人脸库条目（不返回 embedding 内容）。"""
    _ensure_loaded_plugin("face_recognition_suite")
    base = _plugin_dir_abs("face_recognition_suite")
    path = _face_db_path_abs()
    if not str(path).startswith(str(base)):
        raise HTTPException(status_code=400, detail="invalid path")
    if not path.exists():
        return {"exists": False, "items": []}
    raw = _load_face_db_raw(path)
    items = []
    for it in raw.get("identities") or []:
        if not isinstance(it, dict):
            continue
        emb = it.get("embedding")
        if not isinstance(emb, list):
            continue
        items.append(
            {
                "person_id": str(it.get("person_id") or "").strip() or None,
                "name": str(it.get("name") or "").strip() or None,
                "embedding_dim": len(emb),
            }
        )
    return {"exists": True, "items": items}


@router.post("/runtime/face_recognition_suite/face-db/delete")
async def face_db_delete(
    payload: FaceDbDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """删除指定 person_id 的条目（超管）。"""
    _ensure_loaded_plugin("face_recognition_suite")
    pid = str(payload.person_id or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="person_id cannot be empty")
    base = _plugin_dir_abs("face_recognition_suite")
    path = _face_db_path_abs()
    if not str(path).startswith(str(base)):
        raise HTTPException(status_code=400, detail="invalid path")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Face database not found")
    raw = _load_face_db_raw(path)
    before = len(raw.get("identities") or [])
    kept = []
    removed = 0
    for it in raw.get("identities") or []:
        if isinstance(it, dict) and str(it.get("person_id") or "").strip() == pid:
            removed += 1
            continue
        kept.append(it)
    raw["identities"] = kept
    # 防止配置文件写入失败时500无提示
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Face database write failed: {e}")
    try:
        await audit_center_service.log(
            db=db,
            module="plugins",
            action="face_db_delete",
            operator=current_user.username or "unknown",
            result="success",
            summary=f"plugin_id=face_recognition_suite; removed={removed}; before={before}; person_id={pid}",
        )
    except Exception as e:
        logger.warning(f"Error: {e}")
    return {"ok": True, "removed": removed, "before": before, "after": len(kept)}


@router.post("/runtime/face_recognition_suite/face-db/clear")
async def face_db_clear(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """清空人脸库（超管）。"""
    _ensure_loaded_plugin("face_recognition_suite")
    base = _plugin_dir_abs("face_recognition_suite")
    path = _face_db_path_abs()
    if not str(path).startswith(str(base)):
        raise HTTPException(status_code=400, detail="invalid path")
    raw = _load_face_db_raw(path) if path.exists() else {"identities": []}
    before = len(raw.get("identities") or [])
    os.makedirs(str(path.parent), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"identities": []}, f, ensure_ascii=False, indent=2)
    try:
        await audit_center_service.log(
            db=db,
            module="plugins",
            action="face_db_clear",
            operator=current_user.username or "unknown",
            result="success",
            summary=f"plugin_id=face_recognition_suite; before={before}; after=0",
        )
    except Exception as e:
        logger.warning(f"Error: {e}")
    return {"ok": True, "before": before, "after": 0}


# ---------------------------------------------------------------------------
# App version check
# ---------------------------------------------------------------------------

@router.get("/app-version-check")
async def app_version_check(
    plugin_id: str,
    platform: str,
    current_version: str = "0.0.0",
    device_id: str = "",
    release_channel: str = "stable",
):
    """
    App 版本检查（无需登录，供手机版/小程序启动时调用）。
    plugin_id: mobile_app_suite | mini_program_suite
    platform: android | ios | miniprogram
    current_version: 当前客户端版本号，如 1.0.0
    返回是否有更新、最新版本、下载地址、是否强制更新、更新说明。
    """
    if plugin_id not in ("mobile_app_suite", "mini_program_suite"):
        return {
            "has_update": False,
            "latest_version": current_version,
            "download_url": "",
            "force_update": False,
            "release_notes": "",
        }
    meta = plugin_manager.metadata.get(plugin_id)
    config = (meta or {}).get("config_template") or {}
    latest = (config.get("app_version") or "").strip() or "0.0.0"
    min_ver = (config.get("min_app_version") or "").strip()
    release_notes = (config.get("app_release_notes") or "").strip()
    rollout_ratio = int(config.get("rollout_ratio") or 100)
    rollout_ratio = max(0, min(rollout_ratio, 100))
    config_channel = str(config.get("release_channel") or "stable").strip() or "stable"
    allowlist = str(config.get("gray_device_allowlist") or "").strip().replace("，", ",")
    allowlist_set = {x.strip() for x in allowlist.split(",") if x.strip()}
    download_url = ""
    if platform == "android":
        download_url = (config.get("app_download_url_android") or "").strip()
    elif platform == "ios":
        download_url = (config.get("app_download_url_ios") or "").strip()
    elif platform == "miniprogram":
        download_url = (config.get("app_download_url_miniprogram") or "").strip()

    has_update = _version_lt(current_version, latest)
    force_update = bool(min_ver and _version_lt(current_version, min_ver))
    rollout_hit = True
    normalized_channel = (release_channel or "stable").strip() or "stable"
    if normalized_channel != config_channel:
        rollout_hit = False
    if has_update and rollout_hit and rollout_ratio < 100:
        if device_id and device_id in allowlist_set:
            rollout_hit = True
        elif not device_id:
            rollout_hit = False
        else:
            digest = hashlib.md5(f"{plugin_id}:{latest}:{device_id}".encode("utf-8")).hexdigest()
            bucket = int(digest[:8], 16) % 100
            rollout_hit = bucket < rollout_ratio
    has_update = has_update and rollout_hit

    return {
        "has_update": has_update,
        "latest_version": latest,
        "download_url": download_url,
        "force_update": force_update,
        "release_notes": release_notes,
        "rollout_ratio": rollout_ratio,
        "release_channel": config_channel,
    }


# ---------------------------------------------------------------------------
# Runtime config endpoints
# ---------------------------------------------------------------------------

@router.get("/runtime/{plugin_id}/config")
async def get_plugin_runtime_config(
    plugin_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    获取已安装插件的运行时配置（如 mobile_app_suite 的 token_ttl_seconds）。
    供移动端/小程序等客户端读取，与主系统播放鉴权 API 配合使用。
    """
    meta = plugin_manager.metadata.get(plugin_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Plugin not installed or not found")
    tenant_id = (getattr(current_user, "tenant_id", None) or "default").strip() or "default"
    base_config = meta.get("config_template") or {}
    config: dict = dict(base_config) if isinstance(base_config, dict) else {}
    setting_key = f"plugin_runtime_config.{tenant_id}.{plugin_id}"
    result = await db.execute(select(SystemSetting).where(SystemSetting.setting_key == setting_key))
    setting = result.scalars().first()
    if setting and setting.setting_value:
        try:
            saved = json.loads(setting.setting_value)
            if isinstance(saved, dict):
                config.update(saved)
        except Exception as e:
            logger.warning(f"Error: {e}")

    schema = meta.get("config_schema") or {}
    masked = dict(config)
    if isinstance(schema, dict):
        fields = schema.get("fields")
        if isinstance(fields, list):
            for f in fields:
                if not isinstance(f, dict):
                    continue
                key = str(f.get("key") or "").strip()
                if not key:
                    continue
                t = str(f.get("type") or "").strip().lower()
                if t in {"password", "secret"} and key in masked and masked.get(key) not in (None, ""):
                    masked[key] = "******"

    return {"plugin_id": plugin_id, "config": masked, "schema": schema}


@router.put("/runtime/{plugin_id}/config")
async def update_plugin_runtime_config(
    plugin_id: str,
    payload: PluginRuntimeConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("config.manage")),  # 角色检查→权限码检查
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    meta = plugin_manager.metadata.get(plugin_id)
    if not meta:
        await safe_auth_audit(
            db,
            module="plugins",
            action="update_plugin_runtime_config",
            source="plugin_runtime",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="plugin_not_found",
            extra_summary=f"plugin_id={plugin_id}",
        )
        raise HTTPException(status_code=404, detail="Plugin not installed or not found")
    tenant_id = (getattr(current_user, "tenant_id", None) or "default").strip() or "default"
    base_config = meta.get("config_template") or {}
    current: dict = dict(base_config) if isinstance(base_config, dict) else {}

    setting_key = f"plugin_runtime_config.{tenant_id}.{plugin_id}"
    result = await db.execute(select(SystemSetting).where(SystemSetting.setting_key == setting_key))
    setting = result.scalars().first()
    if setting and setting.setting_value:
        try:
            saved = json.loads(setting.setting_value)
            if isinstance(saved, dict):
                current.update(saved)
        except Exception as e:
            logger.warning(f"Error: {e}")

    incoming = payload.config if isinstance(payload.config, dict) else {}
    next_config = dict(current)
    for k, v in incoming.items():
        key = str(k or "").strip()
        if not key:
            continue
        if isinstance(v, str) and v.strip() == "******":
            continue
        next_config[key] = v

    payload_text = json.dumps(next_config, ensure_ascii=False)
    if setting:
        setting.setting_value = payload_text
    else:
        setting = SystemSetting(setting_key=setting_key, setting_value=payload_text)
        db.add(setting)
    await db.commit()

    schema = meta.get("config_schema") or {}
    masked = dict(next_config)
    if isinstance(schema, dict):
        fields = schema.get("fields")
        if isinstance(fields, list):
            for f in fields:
                if not isinstance(f, dict):
                    continue
                key = str(f.get("key") or "").strip()
                if not key:
                    continue
                t = str(f.get("type") or "").strip().lower()
                if t in {"password", "secret"} and key in masked and masked.get(key) not in (None, ""):
                    masked[key] = "******"
    incoming_keys = [str(k or "").strip() for k in (incoming or {}).keys() if str(k or "").strip()]
    keys_hint = ",".join(incoming_keys[:16]) if incoming_keys else "(merge_only)"
    await safe_auth_audit(
        db,
        module="plugins",
        action="update_plugin_runtime_config",
        source="plugin_runtime",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=tenant_id,
        status_code=200,
        detail="ok",
        extra_summary=f"plugin_id={plugin_id}; keys_updated={keys_hint}",
    )
    return {"ok": True, "plugin_id": plugin_id, "config": masked, "schema": schema}


# ---------------------------------------------------------------------------
# Stream health endpoint
# ---------------------------------------------------------------------------

@router.get("/runtime/stream_health/health")
async def stream_health_health(
    app: str | None = None,
    stream: str | None = None,
    only_low_bitrate: bool = False,
    low_bitrate_bytes: int = Query(1024, ge=0),
    min_readers: int = Query(1, ge=0),
    limit: int = Query(500, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    运行时拉取 ZLM getMediaList，并按当前租户通道过滤后返回健康快照。
    用于 `stream_health` 插件的专用运行页展示。
    """

    tenant_id = (getattr(current_user, "tenant_id", None) or "default").strip() or "default"
    # FIX: [2026-08-22 P1] 函数内对导入的模块级缓存变量赋值会使其局部化，读取时触发
    # UnboundLocalError → 500。显式声明 global 以读写模块级缓存。
    global _STREAM_HEALTH_CACHE_RAW, _STREAM_HEALTH_CACHE_META, _STREAM_HEALTH_CACHE_TS
    try:
        resource_gb_ids = (
            await db.execute(select(Resource.gb_id).where(Resource.tenant_id == tenant_id))
        ).scalars().all()
    except Exception:
        resource_gb_ids = []
    resource_gb_id_set = {str(x).strip() for x in resource_gb_ids if x is not None and str(x).strip()}

    # 1) 先尽量复用缓存，减少对 ZLM 的请求
    now_ts = float(datetime.now(timezone.utc).timestamp())
    cache_ttl_sec = 5.0
    async with _STREAM_HEALTH_CACHE_LOCK:
        if (now_ts - _STREAM_HEALTH_CACHE_TS) > cache_ttl_sec or not _STREAM_HEALTH_CACHE_RAW:
            zlm_host, zlm_port, zlm_secret, zlm_node_id, select_reason = await resolve_zlm_api_target(db_session=db)
            url = f"http://{zlm_host}:{zlm_port}/index/api/getMediaList"
            try:
                # FIX [2026-07-17 P1-D1]: secret 通过 POST body 传递
                res = await (await get_http_client()).post(
                    url,
                    data={"secret": zlm_secret},
                    timeout=5,
                )  # 同步requests→异步httpx，避免阻塞事件循环
                payload = res.json()
            except Exception:
                payload = {}

            raw = payload.get("data") if isinstance(payload, dict) else None
            raw_list = raw if isinstance(raw, list) else []

            _STREAM_HEALTH_CACHE_RAW = raw_list
            _STREAM_HEALTH_CACHE_META = {
                "fetched_at": now_ts,
                "zlm_node_id": zlm_node_id,
                "zlm_select_reason": select_reason,
            }
            _STREAM_HEALTH_CACHE_TS = now_ts

    raw_list = _STREAM_HEALTH_CACHE_RAW or []

    # 2) 过滤 + 计算 low bitrate
    rows: list[dict] = []
    low_bitrate_bytes = max(0, int(low_bitrate_bytes))
    min_readers = max(0, int(min_readers))
    limit = max(1, int(limit))

    app_filter = str(app or "").strip()
    stream_filter = str(stream or "").strip()

    for it in raw_list:
        if not isinstance(it, dict):
            continue
        item_app = str(it.get("app") or "").strip()
        item_stream = str(it.get("stream") or "").strip()

        if app_filter and item_app != app_filter:
            continue
        if stream_filter and stream_filter not in item_stream:
            continue
        if resource_gb_id_set and item_stream not in resource_gb_id_set:
            continue

        bytes_speed = it.get("bytesSpeed", 0)
        total_readers = it.get("totalReaderCount", 0)

        try:
            bytes_speed_f = float(bytes_speed or 0)
        except Exception:
            bytes_speed_f = 0.0
        try:
            total_readers_i = int(total_readers or 0)
        except Exception:
            total_readers_i = 0

        is_low = bytes_speed_f < low_bitrate_bytes and total_readers_i > min_readers
        if only_low_bitrate and not is_low:
            continue

        rows.append(
            {
                "app": item_app,
                "stream": item_stream,
                "total_reader_count": total_readers_i,
                "bytes_speed": bytes_speed_f,
                "bytes_speed_kbps": round(bytes_speed_f / 1024.0, 3),
                "is_low_bitrate": is_low,
            }
        )
        if len(rows) >= limit:
            break

    return {
        "plugin_id": "stream_health",
        "rows": rows,
        "meta": dict(_STREAM_HEALTH_CACHE_META or {}),
        "filters": {
            "only_low_bitrate": only_low_bitrate,
            "low_bitrate_bytes": low_bitrate_bytes,
            "min_readers": min_readers,
            "app": app_filter or None,
            "stream": stream_filter or None,
        },
    }


# ---------------------------------------------------------------------------
# Plugin health-status endpoint
# ---------------------------------------------------------------------------

@router.get("/runtime/health-status")
async def plugin_health_status(
    plugin_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    返回已安装插件的运行健康状态。
    前端 PluginCenter / PluginDetail 调用此接口展示插件健康指标。
    """
    # S-02 plugin_manager.list_installed() 不存在，改用 plugins 字典
    installed_ids = list(plugin_manager.plugins.keys())
    if plugin_id:
        installed_ids = [pid for pid in installed_ids if pid == plugin_id]
    items = []
    for pid_str in installed_ids:
        is_healthy = True
        error_count = 0
        last_error = ""
        pid_lower = pid_str.lower()
        if "stream_health" in pid_lower or "health" in pid_lower:
            try:
                from app.core.media_nodes_db import list_db_media_nodes
                nodes = await list_db_media_nodes(db)
                is_healthy = len(nodes) > 0
                if not is_healthy:
                    last_error = "No available media node"  # A-07 中文→英文
                    error_count = 1
            except Exception:
                is_healthy = False
                last_error = "Media node query failed"  # A-07 中文→英文
                error_count = 1
        items.append({
            "plugin_id": pid_str,
            "healthy": is_healthy,
            "error_count": error_count,
            "last_error": last_error,
        })
    return {"items": items}


# ---------------------------------------------------------------------------
# Plugin security-report endpoint
# ---------------------------------------------------------------------------

@router.get("/runtime/security-report")
async def plugin_security_report(
    plugin_id: str | None = None,
    current_user: User = Depends(deps.get_current_active_superuser),
):
    """
    返回已安装插件的安全扫描报告（仅超级管理员可访问）。
    前端 PluginCenter / PluginDetail 调用此接口展示安全风险摘要。
    """
    # S-06 run synchronous os.walk + file scan in thread to avoid blocking event loop
    installed_ids = list(plugin_manager.plugins.keys())
    if plugin_id:
        installed_ids = [pid for pid in installed_ids if pid == plugin_id]

    def _scan_plugin_dir(pid_str: str) -> dict:
        pdir = PLUGIN_DIR_ABS / pid_str
        risks = []
        risk_level = "safe"
        if pdir.is_dir():
            for root, _dirs, files in os.walk(pdir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                            content = fh.read()
                    except Exception:
                        continue
                    if re.search(r"os\.system\s*\(|subprocess\.(call|run|Popen)\s*\(", content):
                        risks.append({"file": os.path.relpath(fpath, pdir), "type": "shell_execution", "severity": "high"})
                    if re.search(r"eval\s*\(|exec\s*\(", content):
                        risks.append({"file": os.path.relpath(fpath, pdir), "type": "code_execution", "severity": "high"})
                    if re.search(r"__import__\s*\(", content):
                        risks.append({"file": os.path.relpath(fpath, pdir), "type": "dynamic_import", "severity": "medium"})
            if any(r["severity"] == "high" for r in risks):
                risk_level = "high_risk"
            elif risks:
                risk_level = "low_risk"
        return {
            "plugin_id": pid_str,
            "risk_level": risk_level,
            "risks": risks,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }

    items = await asyncio.gather(*[
        asyncio.to_thread(_scan_plugin_dir, pid_str) for pid_str in installed_ids
    ])
    return {"items": list(items)}
