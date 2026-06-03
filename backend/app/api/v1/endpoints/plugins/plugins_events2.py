"""
plugins_events2 — 插件运行时事件日志端点（续）：
record_schedule_executor, record_index_verifier, snapshot_refresh,
rtmp_push_channel_monitor, pull_proxy_monitor, mqtt_bridge,
feishu_alert, wecom_alert, sms_alert, alert-test, hook-timeout-test
"""

import os
import re
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path as FSPath

from fastapi import Query, APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.models.user import User
from app.db.session import get_db
from app.core.plugin_manager import plugin_manager, HOOK_ON_ALARM
from app.core.config import settings
from app.services.audit_center_service import audit_center_service
from app.services.auth_audit import safe_auth_audit

from loguru import logger

from .plugins_common import (
    _audit_tid,
    _uuid7_hex,
    require_oss_paid_runtime_from_path,
    AlertTestRequest,
    HookTimeoutTestRequest,
)

router = APIRouter()
@router.get("/runtime/record_index_verifier/events")
async def record_index_verifier_events(
    start_at: str | None = None,
    end_at: str | None = None,
    keyword: str | None = None,
    record_id: str | None = None,
    ok: bool | None = None,
    note: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    录像索引 URL 校验日志（不落盘完整 file_path）：
      [HH:MM:SS.mmm] record_id=<id> ok=true code=<n|-> note=ok|auto_repaired
      [HH:MM:SS.mmm] record_id=<id> ok=false code=<n|-> err=<...>
    """
    plugin_id = "record_index_verifier"

    def _parse_dt(v: str | None) -> datetime | None:
        if not v:
            return None
        try:
            return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception as e:
            logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
            return None

    now = datetime.now()
    dt_end = _parse_dt(end_at) or now
    dt_start = _parse_dt(start_at) or (dt_end - timedelta(hours=24))

    max_span = timedelta(days=3)
    if dt_end < dt_start:
        dt_start, dt_end = dt_end, dt_start
    if (dt_end - dt_start) > max_span:
        dt_start = dt_end - max_span

    start_date = dt_start.date()
    end_date = dt_end.date()

    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 50))

    keyword_text = str(keyword or "").strip().lower()
    rid_filter = str(record_id or "").strip()
    note_filter = str(note or "").strip().lower()
    ok_filter = ok

    line_ok = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+record_id=(?P<rid>\S+)\s+ok=true\s+code=(?P<code>\S+)\s+note=(?P<note>\S+)\s*$"
    )
    line_fail = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+record_id=(?P<rid>\S+)\s+ok=false\s+code=(?P<code>\S+)\s+err=(?P<err>.*)$"
    )

    log_dir = "logs/record_index_verifier"

    def _dec_rid(r: str) -> str:
        return str(r or "").replace("%20", " ")

    def _parse_line(line: str, file_date) -> dict | None:
        if not line:
            return None
        s = line.strip()
        m = line_ok.match(s) or line_fail.match(s)
        if not m:
            return None
        ts_raw = str(m.group("ts") or "").strip()
        rid_raw = _dec_rid(str(m.group("rid") or "").strip())
        code_raw = str(m.group("code") or "").strip()

        if rid_filter and rid_raw != rid_filter:
            return None
        if ok_filter is not None:
            is_ok = line_ok.match(s) is not None
            if is_ok != bool(ok_filter):
                return None
        if note_filter:
            if line_ok.match(s):
                note_v = str(m.group("note") or "").strip().lower()
                if note_v != note_filter:
                    return None
            else:
                return None
        if keyword_text and keyword_text not in s.lower():
            return None

        try:
            t = datetime.strptime(ts_raw, "%H:%M:%S.%f").time()
        except Exception as e:
            logger.debug(f"Non-critical operation failed: {e}")  # A-07 中文日志→英文
            try:
                t = datetime.strptime(ts_raw, "%H:%M:%S").time()
            except Exception as e:
                logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
                return None

        dt = datetime.combine(file_date, t).replace(tzinfo=None)
        if dt < dt_start or dt > dt_end:
            return None

        ok_bool = line_ok.match(s) is not None
        note_v = str(m.groupdict().get("note") or "").strip() if ok_bool else ""
        err_raw = str(m.groupdict().get("err") or "").strip() if not ok_bool else ""

        code_out: int | None
        try:
            code_out = int(code_raw) if code_raw not in {"", "-"} else None
        except Exception as e:
            logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
            code_out = None

        return {
            "ts": dt.isoformat(sep=" "),
            "record_id": rid_raw,
            "ok": ok_bool,
            "code": code_out,
            "code_raw": code_raw,
            "note": note_v,
            "err": err_raw,
            "raw": line[:800],
        }

    collected: list[dict] = []
    target_end_inclusive = page * page_size
    cur_day = end_date
    while cur_day >= start_date:
        file_path = FSPath(log_dir) / f"record_index_verifier_{cur_day.strftime('%Y-%m-%d')}.log"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.read().splitlines()
            except Exception as e:
                logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
                lines = []

            for ln in reversed(lines):
                parsed = _parse_line(ln, cur_day)
                if parsed:
                    collected.append(parsed)
                    if len(collected) >= target_end_inclusive:
                        break

        if len(collected) >= target_end_inclusive:
            break
        cur_day = cur_day - timedelta(days=1)

    start_idx = (page - 1) * page_size
    end_idx = page * page_size
    page_rows = collected[start_idx:end_idx]
    has_more = len(collected) > end_idx

    return {
        "plugin_id": plugin_id,
        "rows": page_rows,
        "meta": {
            "log_dir": log_dir,
            "start_at": dt_start.isoformat(sep=" "),
            "end_at": dt_end.isoformat(sep=" "),
            "page": page,
            "page_size": page_size,
            "has_more": has_more,
            "filters": {
                "keyword": keyword_text or None,
                "record_id": rid_filter or None,
                "ok": ok_filter,
                "note": note_filter or None,
            },
        },
    }


@router.get("/runtime/snapshot_refresh/events")
async def snapshot_refresh_events(
    start_at: str | None = None,
    end_at: str | None = None,
    keyword: str | None = None,
    asset: str | None = None,
    channel: str | None = None,
    ok: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    快照后台刷新日志：
      [HH:MM:SS.mmm] asset=<gb> channel=<gb> stream_type=main|sub ok=true/false [err=...]
    """
    plugin_id = "snapshot_refresh"

    def _parse_dt(v: str | None) -> datetime | None:
        if not v:
            return None
        try:
            return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception as e:
            logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
            return None

    now = datetime.now()
    dt_end = _parse_dt(end_at) or now
    dt_start = _parse_dt(start_at) or (dt_end - timedelta(hours=24))

    max_span = timedelta(days=3)
    if dt_end < dt_start:
        dt_start, dt_end = dt_end, dt_start
    if (dt_end - dt_start) > max_span:
        dt_start = dt_end - max_span

    start_date = dt_start.date()
    end_date = dt_end.date()

    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 50))

    keyword_text = str(keyword or "").strip().lower()
    asset_filter = str(asset or "").strip()
    channel_filter = str(channel or "").strip()
    ok_filter = ok

    line_ok = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+asset=(?P<asset>\S+)\s+channel=(?P<channel>\S+)\s+stream_type=(?P<st>\S+)\s+ok=true\s*$"
    )
    line_fail = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+asset=(?P<asset>\S+)\s+channel=(?P<channel>\S+)\s+stream_type=(?P<st>\S+)\s+ok=false\s+err=(?P<err>.*)$"
    )

    log_dir = "logs/snapshot_refresh"

    def _dec(x: str) -> str:
        return str(x or "").replace("%20", " ")

    def _parse_line(line: str, file_date) -> dict | None:
        if not line:
            return None
        s = line.strip()
        m = line_ok.match(s) or line_fail.match(s)
        if not m:
            return None
        ts_raw = str(m.group("ts") or "").strip()
        asset_raw = _dec(str(m.group("asset") or "").strip())
        channel_raw = _dec(str(m.group("channel") or "").strip())
        st_raw = _dec(str(m.group("st") or "").strip())

        if asset_filter and asset_raw != asset_filter:
            return None
        if channel_filter and channel_raw != channel_filter:
            return None
        if ok_filter is not None:
            is_ok = line_ok.match(s) is not None
            if is_ok != bool(ok_filter):
                return None
        if keyword_text and keyword_text not in s.lower():
            return None

        try:
            t = datetime.strptime(ts_raw, "%H:%M:%S.%f").time()
        except Exception as e:
            logger.debug(f"Non-critical operation failed: {e}")  # A-07 中文日志→英文
            try:
                t = datetime.strptime(ts_raw, "%H:%M:%S").time()
            except Exception as e:
                logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
                return None

        dt = datetime.combine(file_date, t).replace(tzinfo=None)
        if dt < dt_start or dt > dt_end:
            return None

        ok_bool = line_ok.match(s) is not None
        err_raw = str(m.groupdict().get("err") or "").strip() if not ok_bool else ""

        return {
            "ts": dt.isoformat(sep=" "),
            "asset": asset_raw,
            "channel": channel_raw,
            "stream_type": st_raw,
            "ok": ok_bool,
            "err": err_raw,
            "raw": line[:800],
        }

    collected: list[dict] = []
    target_end_inclusive = page * page_size
    cur_day = end_date
    while cur_day >= start_date:
        file_path = FSPath(log_dir) / f"snapshot_refresh_{cur_day.strftime('%Y-%m-%d')}.log"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.read().splitlines()
            except Exception as e:
                logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
                lines = []

            for ln in reversed(lines):
                parsed = _parse_line(ln, cur_day)
                if parsed:
                    collected.append(parsed)
                    if len(collected) >= target_end_inclusive:
                        break

        if len(collected) >= target_end_inclusive:
            break
        cur_day = cur_day - timedelta(days=1)

    start_idx = (page - 1) * page_size
    end_idx = page * page_size
    page_rows = collected[start_idx:end_idx]
    has_more = len(collected) > end_idx

    return {
        "plugin_id": plugin_id,
        "rows": page_rows,
        "meta": {
            "log_dir": log_dir,
            "start_at": dt_start.isoformat(sep=" "),
            "end_at": dt_end.isoformat(sep=" "),
            "page": page,
            "page_size": page_size,
            "has_more": has_more,
            "filters": {
                "keyword": keyword_text or None,
                "asset": asset_filter or None,
                "channel": channel_filter or None,
                "ok": ok_filter,
            },
        },
    }


@router.get("/runtime/rtmp_push_channel_monitor/events")
async def rtmp_push_channel_monitor_events(
    start_at: str | None = None,
    end_at: str | None = None,
    keyword: str | None = None,
    stream: str | None = None,
    source_id: str | None = None,
    evt: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    RTMP 推流通道监控动作日志：
      evt=auto_stop stream=... source_id=... ok=true/false [err=...]
      evt=resource_status stream=... source_id=... status=0|1
    """
    plugin_id = "rtmp_push_channel_monitor"

    def _parse_dt(v: str | None) -> datetime | None:
        if not v:
            return None
        try:
            return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception as e:
            logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
            return None

    now = datetime.now()
    dt_end = _parse_dt(end_at) or now
    dt_start = _parse_dt(start_at) or (dt_end - timedelta(hours=24))

    max_span = timedelta(days=3)
    if dt_end < dt_start:
        dt_start, dt_end = dt_end, dt_start
    if (dt_end - dt_start) > max_span:
        dt_start = dt_end - max_span

    start_date = dt_start.date()
    end_date = dt_end.date()

    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 50))

    keyword_text = str(keyword or "").strip().lower()
    stream_filter = str(stream or "").strip()
    sid_filter = str(source_id or "").strip()
    evt_filter = str(evt or "").strip()
    allowed_evt = {"auto_stop", "resource_status"}
    if evt_filter and evt_filter not in allowed_evt:
        evt_filter = ""

    re_auto_ok = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+evt=auto_stop\s+stream=(?P<stream>\S+)\s+source_id=(?P<sid>\S+)\s+ok=true\s*$"
    )
    re_auto_fail = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+evt=auto_stop\s+stream=(?P<stream>\S+)\s+source_id=(?P<sid>\S+)\s+ok=false\s+err=(?P<err>.*)$"
    )
    re_res = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+evt=resource_status\s+stream=(?P<stream>\S+)\s+source_id=(?P<sid>\S+)\s+status=(?P<status>\d+)\s*$"
    )

    log_dir = "logs/rtmp_push_channel_monitor"

    def _dec(x: str) -> str:
        return str(x or "").replace("%20", " ")

    def _parse_line(line: str, file_date) -> dict | None:
        if not line:
            return None
        s = line.strip()
        m = re_auto_ok.match(s) or re_auto_fail.match(s) or re_res.match(s)
        if not m:
            return None
        ts_raw = str(m.group("ts") or "").strip()
        stream_raw = _dec(str(m.group("stream") or "").strip())
        sid_raw = _dec(str(m.group("sid") or "").strip())

        ev = "auto_stop" if re_auto_ok.match(s) or re_auto_fail.match(s) else "resource_status"
        if evt_filter and ev != evt_filter:
            return None
        if stream_filter and stream_raw != stream_filter:
            return None
        if sid_filter and sid_raw != sid_filter:
            return None
        if keyword_text and keyword_text not in s.lower():
            return None

        try:
            t = datetime.strptime(ts_raw, "%H:%M:%S.%f").time()
        except Exception as e:
            logger.debug(f"Non-critical operation failed: {e}")  # A-07 中文日志→英文
            try:
                t = datetime.strptime(ts_raw, "%H:%M:%S").time()
            except Exception as e:
                logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
                return None

        dt = datetime.combine(file_date, t).replace(tzinfo=None)
        if dt < dt_start or dt > dt_end:
            return None

        if re_res.match(s):
            try:
                st_v = int(m.group("status"))
            except Exception as e:
                logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
                st_v = None
            return {
                "ts": dt.isoformat(sep=" "),
                "evt": "resource_status",
                "stream": stream_raw,
                "source_id": sid_raw,
                "status": st_v,
                "ok": None,
                "err": "",
                "raw": line[:800],
            }

        ok_bool = re_auto_ok.match(s) is not None
        err_raw = str(m.groupdict().get("err") or "").strip() if not ok_bool else ""
        return {
            "ts": dt.isoformat(sep=" "),
            "evt": "auto_stop",
            "stream": stream_raw,
            "source_id": sid_raw,
            "status": None,
            "ok": ok_bool,
            "err": err_raw,
            "raw": line[:800],
        }

    collected: list[dict] = []
    target_end_inclusive = page * page_size
    cur_day = end_date
    while cur_day >= start_date:
        file_path = FSPath(log_dir) / f"rtmp_push_channel_monitor_{cur_day.strftime('%Y-%m-%d')}.log"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.read().splitlines()
            except Exception as e:
                logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
                lines = []

            for ln in reversed(lines):
                parsed = _parse_line(ln, cur_day)
                if parsed:
                    collected.append(parsed)
                    if len(collected) >= target_end_inclusive:
                        break

        if len(collected) >= target_end_inclusive:
            break
        cur_day = cur_day - timedelta(days=1)

    start_idx = (page - 1) * page_size
    end_idx = page * page_size
    page_rows = collected[start_idx:end_idx]
    has_more = len(collected) > end_idx

    return {
        "plugin_id": plugin_id,
        "rows": page_rows,
        "meta": {
            "log_dir": log_dir,
            "start_at": dt_start.isoformat(sep=" "),
            "end_at": dt_end.isoformat(sep=" "),
            "page": page,
            "page_size": page_size,
            "has_more": has_more,
            "filters": {
                "keyword": keyword_text or None,
                "stream": stream_filter or None,
                "source_id": sid_filter or None,
                "evt": evt_filter or None,
            },
        },
    }


@router.get("/runtime/pull_proxy_monitor/events")
async def pull_proxy_monitor_events(
    start_at: str | None = None,
    end_at: str | None = None,
    keyword: str | None = None,
    stream: str | None = None,
    evt: str | None = None,
    ok: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    拉流代理监控动作日志：
      [HH:MM:SS.mmm] evt=auto_stop|auto_retry stream=<name> ok=true/false [err=...]
    """
    plugin_id = "pull_proxy_monitor"

    def _parse_dt(v: str | None) -> datetime | None:
        if not v:
            return None
        try:
            return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception as e:
            logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
            return None

    now = datetime.now()
    dt_end = _parse_dt(end_at) or now
    dt_start = _parse_dt(start_at) or (dt_end - timedelta(hours=24))

    max_span = timedelta(days=3)
    if dt_end < dt_start:
        dt_start, dt_end = dt_end, dt_start
    if (dt_end - dt_start) > max_span:
        dt_start = dt_end - max_span

    start_date = dt_start.date()
    end_date = dt_end.date()

    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 50))

    keyword_text = str(keyword or "").strip().lower()
    stream_filter = str(stream or "").strip()
    evt_filter = str(evt or "").strip().lower()
    if evt_filter and evt_filter not in {"auto_stop", "auto_retry"}:
        evt_filter = ""
    ok_filter = ok

    line_ok = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+evt=(?P<evt>auto_stop|auto_retry)\s+stream=(?P<stream>\S+)\s+ok=true\s*$"
    )
    line_fail = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+evt=(?P<evt>auto_stop|auto_retry)\s+stream=(?P<stream>\S+)\s+ok=false\s+err=(?P<err>.*)$"
    )

    log_dir = "logs/pull_proxy_monitor"

    def _dec(x: str) -> str:
        return str(x or "").replace("%20", " ")

    def _parse_line(line: str, file_date) -> dict | None:
        if not line:
            return None
        s = line.strip()
        m = line_ok.match(s) or line_fail.match(s)
        if not m:
            return None
        ts_raw = str(m.group("ts") or "").strip()
        evt_v = str(m.group("evt") or "").strip()
        stream_raw = _dec(str(m.group("stream") or "").strip())

        if evt_filter and evt_v != evt_filter:
            return None
        if stream_filter and stream_raw != stream_filter:
            return None
        if ok_filter is not None:
            is_ok = line_ok.match(s) is not None
            if is_ok != bool(ok_filter):
                return None
        if keyword_text and keyword_text not in s.lower():
            return None

        try:
            t = datetime.strptime(ts_raw, "%H:%M:%S.%f").time()
        except Exception as e:
            logger.debug(f"Non-critical operation failed: {e}")  # A-07 中文日志→英文
            try:
                t = datetime.strptime(ts_raw, "%H:%M:%S").time()
            except Exception as e:
                logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
                return None

        dt = datetime.combine(file_date, t).replace(tzinfo=None)
        if dt < dt_start or dt > dt_end:
            return None

        ok_bool = line_ok.match(s) is not None
        err_raw = str(m.groupdict().get("err") or "").strip() if not ok_bool else ""

        return {
            "ts": dt.isoformat(sep=" "),
            "evt": evt_v,
            "stream": stream_raw,
            "ok": ok_bool,
            "err": err_raw,
            "raw": line[:800],
        }

    collected: list[dict] = []
    target_end_inclusive = page * page_size
    cur_day = end_date
    while cur_day >= start_date:
        file_path = FSPath(log_dir) / f"pull_proxy_monitor_{cur_day.strftime('%Y-%m-%d')}.log"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.read().splitlines()
            except Exception as e:
                logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
                lines = []

            for ln in reversed(lines):
                parsed = _parse_line(ln, cur_day)
                if parsed:
                    collected.append(parsed)
                    if len(collected) >= target_end_inclusive:
                        break

        if len(collected) >= target_end_inclusive:
            break
        cur_day = cur_day - timedelta(days=1)

    start_idx = (page - 1) * page_size
    end_idx = page * page_size
    page_rows = collected[start_idx:end_idx]
    has_more = len(collected) > end_idx

    return {
        "plugin_id": plugin_id,
        "rows": page_rows,
        "meta": {
            "log_dir": log_dir,
            "start_at": dt_start.isoformat(sep=" "),
            "end_at": dt_end.isoformat(sep=" "),
            "page": page,
            "page_size": page_size,
            "has_more": has_more,
            "filters": {
                "keyword": keyword_text or None,
                "stream": stream_filter or None,
                "evt": evt_filter or None,
                "ok": ok_filter,
            },
        },
    }


@router.get("/runtime/mqtt_bridge/events")
async def mqtt_bridge_events(
    start_at: str | None = None,
    end_at: str | None = None,
    keyword: str | None = None,
    device: str | None = None,
    kind: str | None = None,
    alarm_type: str | None = None,
    ok: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    MQTT 桥接发布日志：
      kind=device_status device=<id> ok=true/false [err=...]
      kind=alarm device=<id> alarm_type=<t> ok=true/false [err=...]
    """
    plugin_id = "mqtt_bridge"

    def _parse_dt(v: str | None) -> datetime | None:
        if not v:
            return None
        try:
            return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception as e:
            logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
            return None

    now = datetime.now()
    dt_end = _parse_dt(end_at) or now
    dt_start = _parse_dt(start_at) or (dt_end - timedelta(hours=24))

    max_span = timedelta(days=3)
    if dt_end < dt_start:
        dt_start, dt_end = dt_end, dt_start
    if (dt_end - dt_start) > max_span:
        dt_start = dt_end - max_span

    start_date = dt_start.date()
    end_date = dt_end.date()

    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 50))

    keyword_text = str(keyword or "").strip().lower()
    device_filter = str(device or "").strip()
    kind_filter = str(kind or "").strip().lower()
    if kind_filter and kind_filter not in {"device_status", "alarm"}:
        kind_filter = ""
    atype_filter = str(alarm_type or "").strip()
    ok_filter = ok

    re_ds_ok = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+kind=device_status\s+device=(?P<device>\S+)\s+ok=true\s*$"
    )
    re_ds_fail = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+kind=device_status\s+device=(?P<device>\S+)\s+ok=false\s+err=(?P<err>.*)$"
    )
    re_al_ok = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+kind=alarm\s+device=(?P<device>\S+)\s+alarm_type=(?P<atype>\S+)\s+ok=true\s*$"
    )
    re_al_fail = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+kind=alarm\s+device=(?P<device>\S+)\s+alarm_type=(?P<atype>\S+)\s+ok=false\s+err=(?P<err>.*)$"
    )

    log_dir = "logs/mqtt_bridge"

    def _dec(x: str) -> str:
        return str(x or "").replace("%20", " ")

    def _parse_line(line: str, file_date) -> dict | None:
        if not line:
            return None
        s = line.strip()
        m = re_ds_ok.match(s) or re_ds_fail.match(s) or re_al_ok.match(s) or re_al_fail.match(s)
        if not m:
            return None
        ts_raw = str(m.group("ts") or "").strip()
        kind_v = "device_status" if (re_ds_ok.match(s) or re_ds_fail.match(s)) else "alarm"
        device_raw = _dec(str(m.group("device") or "").strip())

        if kind_filter and kind_v != kind_filter:
            return None
        if device_filter and device_raw != device_filter:
            return None

        at_raw = ""
        if kind_v == "alarm":
            at_raw = _dec(str(m.group("atype") or "").strip())
            if atype_filter and at_raw != atype_filter:
                return None

        if ok_filter is not None:
            is_ok = bool(re_ds_ok.match(s) or re_al_ok.match(s))
            if is_ok != bool(ok_filter):
                return None
        if keyword_text and keyword_text not in s.lower():
            return None

        try:
            t = datetime.strptime(ts_raw, "%H:%M:%S.%f").time()
        except Exception as e:
            logger.debug(f"Non-critical operation failed: {e}")  # A-07 中文日志→英文
            try:
                t = datetime.strptime(ts_raw, "%H:%M:%S").time()
            except Exception as e:
                logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
                return None

        dt = datetime.combine(file_date, t).replace(tzinfo=None)
        if dt < dt_start or dt > dt_end:
            return None

        ok_bool = bool(re_ds_ok.match(s) or re_al_ok.match(s))
        err_raw = str(m.groupdict().get("err") or "").strip() if not ok_bool else ""

        return {
            "ts": dt.isoformat(sep=" "),
            "kind": kind_v,
            "device": device_raw,
            "alarm_type": at_raw,
            "ok": ok_bool,
            "err": err_raw,
            "raw": line[:800],
        }

    collected: list[dict] = []
    target_end_inclusive = page * page_size
    cur_day = end_date
    while cur_day >= start_date:
        file_path = FSPath(log_dir) / f"mqtt_bridge_{cur_day.strftime('%Y-%m-%d')}.log"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.read().splitlines()
            except Exception as e:
                logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
                lines = []

            for ln in reversed(lines):
                parsed = _parse_line(ln, cur_day)
                if parsed:
                    collected.append(parsed)
                    if len(collected) >= target_end_inclusive:
                        break

        if len(collected) >= target_end_inclusive:
            break
        cur_day = cur_day - timedelta(days=1)

    start_idx = (page - 1) * page_size
    end_idx = page * page_size
    page_rows = collected[start_idx:end_idx]
    has_more = len(collected) > end_idx

    return {
        "plugin_id": plugin_id,
        "rows": page_rows,
        "meta": {
            "log_dir": log_dir,
            "start_at": dt_start.isoformat(sep=" "),
            "end_at": dt_end.isoformat(sep=" "),
            "page": page,
            "page_size": page_size,
            "has_more": has_more,
            "filters": {
                "keyword": keyword_text or None,
                "device": device_filter or None,
                "kind": kind_filter or None,
                "alarm_type": atype_filter or None,
                "ok": ok_filter,
            },
        },
    }


def _alert_plugin_push_events_payload(
    *,
    plugin_id: str,
    log_dir: str,
    log_filename_prefix: str,
    start_at: str | None,
    end_at: str | None,
    keyword: str | None,
    device: str | None,
    alarm_type: str | None,
    ok: bool | None,
    page: int,
    page_size: int,
) -> dict:
    """
    告警推送插件结构化日志（与 feishu/wecom/sms 一致）：
      [HH:MM:SS.mmm] device=<id> alarm_type=<t> ok=true/false [err=...]
    """

    def _parse_dt(v: str | None) -> datetime | None:
        if not v:
            return None
        try:
            return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception as e:
            logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
            return None

    now = datetime.now()
    dt_end = _parse_dt(end_at) or now
    dt_start = _parse_dt(start_at) or (dt_end - timedelta(hours=24))

    max_span = timedelta(days=3)
    if dt_end < dt_start:
        dt_start, dt_end = dt_end, dt_start
    if (dt_end - dt_start) > max_span:
        dt_start = dt_end - max_span

    start_date = dt_start.date()
    end_date = dt_end.date()

    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 50))

    keyword_text = str(keyword or "").strip().lower()
    device_filter = str(device or "").strip()
    atype_filter = str(alarm_type or "").strip()
    ok_filter = ok

    line_ok = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+device=(?P<device>\S+)\s+alarm_type=(?P<atype>\S+)\s+ok=true\s*$"
    )
    line_fail = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+device=(?P<device>\S+)\s+alarm_type=(?P<atype>\S+)\s+ok=false\s+err=(?P<err>.*)$"
    )

    def _dec(x: str) -> str:
        return str(x or "").replace("%20", " ")

    def _parse_line(line: str, file_date) -> dict | None:
        if not line:
            return None
        s = line.strip()
        m = line_ok.match(s) or line_fail.match(s)
        if not m:
            return None
        ts_raw = str(m.group("ts") or "").strip()
        device_raw = _dec(str(m.group("device") or "").strip())
        at_raw = _dec(str(m.group("atype") or "").strip())

        if device_filter and device_raw != device_filter:
            return None
        if atype_filter and at_raw != atype_filter:
            return None
        if ok_filter is not None:
            is_ok = line_ok.match(s) is not None
            if is_ok != bool(ok_filter):
                return None
        if keyword_text and keyword_text not in s.lower():
            return None

        try:
            t = datetime.strptime(ts_raw, "%H:%M:%S.%f").time()
        except Exception as e:
            logger.debug(f"Non-critical operation failed: {e}")  # A-07 中文日志→英文
            try:
                t = datetime.strptime(ts_raw, "%H:%M:%S").time()
            except Exception as e:
                logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
                return None

        dt = datetime.combine(file_date, t).replace(tzinfo=None)
        if dt < dt_start or dt > dt_end:
            return None

        ok_bool = line_ok.match(s) is not None
        err_raw = str(m.groupdict().get("err") or "").strip() if not ok_bool else ""

        return {
            "ts": dt.isoformat(sep=" "),
            "device": device_raw,
            "alarm_type": at_raw,
            "ok": ok_bool,
            "err": err_raw,
            "raw": line[:800],
        }

    collected: list[dict] = []
    target_end_inclusive = page * page_size
    cur_day = end_date
    while cur_day >= start_date:
        file_path = FSPath(log_dir) / f"{log_filename_prefix}_{cur_day.strftime('%Y-%m-%d')}.log"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.read().splitlines()
            except Exception as e:
                logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
                lines = []

            for ln in reversed(lines):
                parsed = _parse_line(ln, cur_day)
                if parsed:
                    collected.append(parsed)
                    if len(collected) >= target_end_inclusive:
                        break

        if len(collected) >= target_end_inclusive:
            break
        cur_day = cur_day - timedelta(days=1)

    start_idx = (page - 1) * page_size
    end_idx = page * page_size
    page_rows = collected[start_idx:end_idx]
    has_more = len(collected) > end_idx

    return {
        "plugin_id": plugin_id,
        "rows": page_rows,
        "meta": {
            "log_dir": log_dir,
            "start_at": dt_start.isoformat(sep=" "),
            "end_at": dt_end.isoformat(sep=" "),
            "page": page,
            "page_size": page_size,
            "has_more": has_more,
            "filters": {
                "keyword": keyword_text or None,
                "device": device_filter or None,
                "alarm_type": atype_filter or None,
                "ok": ok_filter,
            },
        },
    }


@router.get("/runtime/feishu_alert/events")
async def feishu_alert_events(
    start_at: str | None = None,
    end_at: str | None = None,
    keyword: str | None = None,
    device: str | None = None,
    alarm_type: str | None = None,
    ok: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """飞书告警推送日志。"""
    return _alert_plugin_push_events_payload(
        plugin_id="feishu_alert",
        log_dir="logs/feishu_alert",
        log_filename_prefix="feishu_alert",
        start_at=start_at,
        end_at=end_at,
        keyword=keyword,
        device=device,
        alarm_type=alarm_type,
        ok=ok,
        page=page,
        page_size=page_size,
    )


@router.get("/runtime/wecom_alert/events")
async def wecom_alert_events(
    start_at: str | None = None,
    end_at: str | None = None,
    keyword: str | None = None,
    device: str | None = None,
    alarm_type: str | None = None,
    ok: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """企业微信告警推送日志。"""
    return _alert_plugin_push_events_payload(
        plugin_id="wecom_alert",
        log_dir="logs/wecom_alert",
        log_filename_prefix="wecom_alert",
        start_at=start_at,
        end_at=end_at,
        keyword=keyword,
        device=device,
        alarm_type=alarm_type,
        ok=ok,
        page=page,
        page_size=page_size,
    )


@router.get("/runtime/sms_alert/events")
async def sms_alert_events(
    start_at: str | None = None,
    end_at: str | None = None,
    keyword: str | None = None,
    device: str | None = None,
    alarm_type: str | None = None,
    ok: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """短信告警推送日志。"""
    return _alert_plugin_push_events_payload(
        plugin_id="sms_alert",
        log_dir="logs/sms_alert",
        log_filename_prefix="sms_alert",
        start_at=start_at,
        end_at=end_at,
        keyword=keyword,
        device=device,
        alarm_type=alarm_type,
        ok=ok,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# Alert test & Hook timeout test endpoints
# ---------------------------------------------------------------------------

@router.post("/alert-test")
async def alert_test(
    payload: AlertTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("config.manage")),  # 角色检查→权限码检查
):
    """
    触发一次测试告警，走与真实报警相同的 HOOK_ON_ALARM 流程：
    - 将构造一条内存中的测试 Alarm 对象，不落库
    - 交由已安装的 sms_alert / wecom_alert / feishu_alert 等插件处理
    """

    class _TestAlarm:
        def __init__(self, user: User, target: str | None = None, test_channel: str = "all"):
            self.id = "test-alarm"
            self.tenant_id = user.tenant_id or "default"
            self.device_id = "TEST_DEVICE"
            self.channel_id = "TEST_CHANNEL"
            self.priority = "3"
            self.method = "Test"
            from datetime import datetime

            self.time = datetime.now(timezone.utc)
            self.description = f"Third-party alert channel test (triggered by={user.username})"  # A-07 中文→英文
            if target:
                self.description += f" target={target}"
            self.alarm_type = "TestNotification"
            self.test_channel = test_channel  # all | sms_alert | wecom_alert | feishu_alert

    channel = (payload.channel or "all").strip().lower()
    if channel not in ("all", "sms_alert", "wecom_alert", "feishu_alert"):
        channel = "all"
    alarm = _TestAlarm(current_user, payload.target, test_channel=channel)

    await plugin_manager.emit(HOOK_ON_ALARM, alarm)

    msg = "Test alert triggered, please check the corresponding channel for receipt."  # A-07 中文→英文
    if channel != "all":
        names = {"sms_alert": "SMS", "wecom_alert": "WeCom", "feishu_alert": "Feishu"}  # A-07 中文→英文
        msg = f"Only {names.get(channel, channel)} channel test triggered, please check that channel."  # A-07 中文→英文
    tgt = (payload.target or "").replace(";", ".")[:64]
    await safe_auth_audit(
        db,
        module="plugins",
        action="alert_channel_test",
        source="plugin_alert_test",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"channel={channel}; target_hint={tgt or 'none'}",
    )
    return {"status": "ok", "message": msg}


def _hook_timeout_test_sleep_cb(payload: dict):
    """模块级同步回调：用于进程模式下的 Hook 超时验证。"""
    sleep_seconds = float(payload.get("sleep_seconds") or 0)
    time.sleep(sleep_seconds)


@router.post("/hook-timeout-test")
async def hook_timeout_test(
    payload: HookTimeoutTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("config.manage")),  # 角色检查→权限码检查
):
    timeout_seconds = float(getattr(settings, "PLUGIN_HOOK_EXEC_TIMEOUT_SECONDS", 0) or 0)
    if timeout_seconds <= 0:
        raise HTTPException(
            status_code=400,
            detail="PLUGIN_HOOK_EXEC_TIMEOUT_SECONDS <= 0: Hook timeout isolation not enabled, cannot verify.",  # i18n
        )

    hook_name = (payload.hook_name or "").strip()
    if not hook_name:
        raise HTTPException(status_code=400, detail="hook_name cannot be empty")
    if hook_name == HOOK_ON_ALARM:
        raise HTTPException(status_code=400, detail="hook_name cannot be on_alarm to avoid recursive triggers。")
    if hook_name not in plugin_manager.hooks:
        raise HTTPException(status_code=400, detail=f"Unknown hook_name: {hook_name}")  # i18n

    sleep_seconds = float(payload.sleep_seconds) if payload.sleep_seconds is not None else (timeout_seconds + 0.8)
    if sleep_seconds <= timeout_seconds:
        sleep_seconds = timeout_seconds + 0.3

    alarm_event = asyncio.Event()
    captured: dict | None = None

    test_id = _uuid7_hex(12)
    log_dir = os.path.join("logs", "plugin_hook_timeout_test")
    log_path: str | None = None
    if payload.log_to_file:
        os.makedirs(log_dir, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_path = os.path.join(log_dir, f"hook_timeout_test_{today}.jsonl")

    async def _on_alarm_capture(alarm):
        nonlocal captured
        try:
            if hasattr(alarm, "__dict__"):
                alarm_dict = dict(alarm.__dict__)
            elif isinstance(alarm, dict):
                alarm_dict = dict(alarm)
            else:
                alarm_dict = {"value": str(alarm)}
        except Exception as e:
            logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
            alarm_dict = {"value": "unserializable"}

        captured = alarm_dict
        alarm_event.set()

        if log_path:
            try:
                record = {
                    "test_id": test_id,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "alarm": alarm_dict,
                }
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.debug(f"Non-critical operation failed: {e}")  # A-07 中文日志→英文

    plugin_manager.register_hook(HOOK_ON_ALARM, _on_alarm_capture)
    plugin_manager.register_hook(hook_name, _hook_timeout_test_sleep_cb)
    timed_out_capture = False

    try:
        await plugin_manager.emit(
            hook_name,
            {"sleep_seconds": sleep_seconds, "test_id": test_id},
        )
        try:
            await asyncio.wait_for(alarm_event.wait(), timeout=float(payload.alarm_capture_timeout_seconds))
        except asyncio.TimeoutError:
            timed_out_capture = True
    finally:
        try:
            plugin_manager.hooks.get(HOOK_ON_ALARM, []).remove(_on_alarm_capture)
        except ValueError:
            logger.warning("ValueError occurred")
        try:
            plugin_manager.hooks.get(hook_name, []).remove(_hook_timeout_test_sleep_cb)
        except ValueError:
            logger.warning("ValueError occurred")

    result = "success" if captured else "no_alarm_captured"
    await safe_auth_audit(
        db,
        module="plugins",
        action="hook_timeout_test",
        source="plugin_hook_timeout_test",
        operator=current_user.username or "unknown",
        result=result,
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"hook_name={hook_name}; sleep_seconds={sleep_seconds:.2f}; timed_out_capture={timed_out_capture}",
    )

    return {
        "status": "ok",
        "test_id": test_id,
        "hook_name": hook_name,
        "expected_timeout_seconds": timeout_seconds,
        "sleep_seconds": sleep_seconds,
        "alarm_captured": captured is not None,
        "alarm": captured,
        "log_path": log_path,
        "note": "If no alarm was captured, it may be because HOOK_ON_ALARM has no available alert plugin configured (but this endpoint should still write to the local log).",  # A-07 中文→英文
    }