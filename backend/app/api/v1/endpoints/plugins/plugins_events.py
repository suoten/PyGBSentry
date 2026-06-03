"""
plugins_events — 插件运行时事件日志端点（sip_logger, network_watchdog, stream_idle, timelapse,
webhook_pusher, s3_sync, ptz_tour, auto_record, record_schedule_executor,
record_index_verifier, snapshot_refresh, rtmp_push_channel_monitor,
pull_proxy_monitor, mqtt_bridge, feishu_alert, wecom_alert, sms_alert）
以及告警测试和 Hook 超时测试端点。
"""

import re
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path as FSPath

from fastapi import Query, APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.models.user import User
from app.models.system_setting import SystemSetting
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
    HOOK_ON_ALARM as HOOK_ON_ALARM_CONST,
)

router = APIRouter()


@router.get("/runtime/sip_logger/logs")
async def sip_logger_logs(
    start_at: str | None = None,
    end_at: str | None = None,
    keyword: str | None = None,
    direction: str | None = None,  # inbound/outbound
    proto: str | None = None,  # UDP/TCP
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    运行时读取 `sip_logger` 写入的日志文件（logs/sip_audit/sip_YYYY-MM-DD.log）。
    提供时间范围/关键字/方向/协议过滤 + 分页（新到旧）。
    """

    plugin_id = "sip_logger"
    tenant_id = (getattr(current_user, "tenant_id", None) or "default").strip() or "default"

    # 读取 sip_logger 的运行时 log_dir
    meta = plugin_manager.metadata.get(plugin_id) or {}
    base_config = meta.get("config_template") or {}
    log_dir = str(base_config.get("log_dir") or "logs/sip_audit")
    setting_key = f"plugin_runtime_config.{tenant_id}.{plugin_id}"
    try:
        result = await db.execute(select(SystemSetting).where(SystemSetting.setting_key == setting_key))
        setting = result.scalars().first()
        if setting and setting.setting_value:
            saved = json.loads(setting.setting_value)
            if isinstance(saved, dict) and saved.get("log_dir"):
                log_dir = str(saved.get("log_dir") or log_dir)
    except Exception as e:
        logger.debug(f"Non-critical operation failed: {e}")  # A-07 中文日志→英文

    def _parse_dt(v: str | None) -> datetime | None:
        if not v:
            return None
        try:
            # 前端使用 value-format: "YYYY-MM-DDTHH:mm:ss"（无时区）
            return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception as e:
            logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
            return None

    now = datetime.now()
    dt_end = _parse_dt(end_at) or now
    dt_start = _parse_dt(start_at) or (dt_end - timedelta(hours=24))

    # 安全限制：最多查 3 天，避免误操作导致 IO 压力
    try:
        max_span = timedelta(days=3)
        if dt_end < dt_start:
            dt_start, dt_end = dt_end, dt_start
        if (dt_end - dt_start) > max_span:
            dt_start = dt_end - max_span
    except Exception as e:
        logger.debug(f"Non-critical operation failed: {e}")  # A-07 中文日志→英文

    start_date = dt_start.date()
    end_date = dt_end.date()

    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 50))
    target_end_inclusive = page * page_size  # 需要收集到这个数量以判断 has_more

    keyword_text = str(keyword or "").strip()
    direction_filter = str(direction or "").strip().lower()
    proto_filter = str(proto or "").strip().upper()

    # 日志第一行格式：
    # [{timestamp}] [{direction}] [{proto}] {ip}:{port}
    line_re = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+\[(?P<direction>[^\]]+)\]\s+\[(?P<proto>[^\]]+)\]\s+(?P<addr>.+)$"
    )
    sep_line = "--------------------------------------------------"

    def _parse_block(block_text: str, file_date) -> dict | None:
        if not block_text:
            return None
        # 找第一行非空
        first = ""
        for ln in block_text.splitlines():
            s = (ln or "").strip()
            if s:
                first = s
                break
        if not first:
            return None
        m = line_re.match(first)
        if not m:
            return None
        ts_raw = str(m.group("ts") or "").strip()
        d_raw = str(m.group("direction") or "").strip()
        p_raw = str(m.group("proto") or "").strip()
        addr_raw = str(m.group("addr") or "").strip()

        # parse timestamp: HH:MM:SS.xxx
        try:
            t = datetime.strptime(ts_raw, "%H:%M:%S.%f").time()
        except Exception as e:
            logger.debug(f"Non-critical operation failed: {e}")  # A-07 中文日志→英文
            try:
                t = datetime.strptime(ts_raw, "%H:%M:%S").time()
            except Exception as e:
                logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
                return None
        dt = datetime.combine(file_date, t)

        if dt < dt_start or dt > dt_end:
            return None
        if direction_filter and d_raw.lower() != direction_filter:
            return None
        if proto_filter and p_raw.upper() != proto_filter:
            return None
        if keyword_text:
            if keyword_text.lower() not in block_text.lower():
                return None

        # 截断 raw，避免一次返回太大
        raw = block_text.strip()
        snippet = raw[:600]

        return {
            "ts": dt.isoformat(sep=" "),
            "direction": d_raw,
            "proto": p_raw,
            "addr": addr_raw,
            "snippet": snippet,
        }

    def _iter_log_entries_for_date(date_obj) -> list[dict]:
        file_path = FSPath(log_dir) / f"sip_{date_obj.strftime('%Y-%m-%d')}.log"
        if not file_path.exists():
            return []
        blocks: list[str] = []
        buf: list[str] = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    ln = line.rstrip("\n")
                    if ln.strip() == sep_line:
                        buf.append(ln)
                        blocks.append("\n".join(buf))
                        buf = []
                    else:
                        buf.append(ln)
            if buf:
                blocks.append("\n".join(buf))
        except Exception as e:
            logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
            return []

        out: list[dict] = []
        for b in blocks:
            parsed = _parse_block(b, date_obj)
            if parsed:
                out.append(parsed)
        return out

    # 按 desc（新到旧）收集：先遍历日期降序
    collected: list[dict] = []
    need_collect = target_end_inclusive + 1
    cur_day = end_date
    while cur_day >= start_date:
        entries = _iter_log_entries_for_date(cur_day)
        entries.reverse()
        for e in entries:
            collected.append(e)
            if len(collected) >= need_collect:
                break
        if len(collected) >= need_collect:
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
                "direction": direction_filter or None,
                "proto": proto_filter or None,
            },
        },
    }


@router.get("/runtime/network_watchdog/events")
async def network_watchdog_events(
    start_at: str | None = None,
    end_at: str | None = None,
    keyword: str | None = None,
    device: str | None = None,
    ip: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    查询 `network_watchdog` 写入的文件日志：
      [HH:MM:SS.mmm] device=<gb_id> ip=<ip> unreachable
    提供分页与过滤：关键字/设备/网卡 IP。
    """
    plugin_id = "network_watchdog"

    # 读取/保留与 sip_logger 一致的时间处理方式（无时区 iso 字符串）
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

    # 安全限制：最多查 3 天
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
    ip_filter = str(ip or "").strip()

    # 解析行
    # [12:34:56.789] device=3402... ip=1.2.3.4 unreachable
    line_re = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+device=(?P<device>\S+)\s+ip=(?P<ip>\S+)\s+(?P<msg>.+)$"
    )

    log_dir = "logs/network_watchdog"

    def _parse_line(line: str, file_date) -> dict | None:
        if not line:
            return None
        m = line_re.match(line.strip())
        if not m:
            return None
        ts_raw = str(m.group("ts") or "").strip()
        device_raw = str(m.group("device") or "").strip()
        ip_raw = str(m.group("ip") or "").strip()
        msg_raw = str(m.group("msg") or "").strip()

        if device_filter and device_raw != device_filter:
            return None
        if ip_filter and ip_raw != ip_filter:
            return None
        if keyword_text and keyword_text not in line.lower():
            return None

        # parse time
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

        return {
            "ts": dt.isoformat(sep=" "),
            "device": device_raw,
            "ip": ip_raw,
            "message": msg_raw,
            "raw": line[:800],
        }

    # 收集：新到旧。以日期文件逆序扫描
    collected: list[dict] = []
    target_end_inclusive = page * page_size
    cur_day = end_date
    while cur_day >= start_date:
        file_path = FSPath(log_dir) / f"network_watchdog_{cur_day.strftime('%Y-%m-%d')}.log"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.read().splitlines()
            except Exception as e:
                logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
                lines = []
            # 新到旧：文件内也按时间（近似）反转
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
                "ip": ip_filter or None,
            },
        },
    }


@router.get("/runtime/stream_idle/events")
async def stream_idle_events(
    start_at: str | None = None,
    end_at: str | None = None,
    keyword: str | None = None,
    app: str | None = None,
    stream: str | None = None,
    node: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    查询 `stream_idle` 写入的文件日志：
      [HH:MM:SS.mmm] app=<app> stream=<stream> node=<node_id> start=<iso> duration_s=<N> reason=plugin_stream_idle
    """
    plugin_id = "stream_idle"

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
    app_filter = str(app or "").strip()
    stream_filter = str(stream or "").strip()
    node_filter = str(node or "").strip()

    # 注意：日志中的 start 字段无空格（isoformat 默认含 'T'）
    line_re = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+app=(?P<app>\S+)\s+stream=(?P<stream>\S+)\s+node=(?P<node>\S*)\s+start=(?P<start>\S+)\s+duration_s=(?P<dur>\d+)\s+reason=(?P<reason>.+)$"
    )

    log_dir = "logs/stream_idle"

    def _parse_line(line: str, file_date) -> dict | None:
        if not line:
            return None
        m = line_re.match(line.strip())
        if not m:
            return None
        ts_raw = str(m.group("ts") or "").strip()
        app_raw = str(m.group("app") or "").strip()
        stream_raw = str(m.group("stream") or "").strip()
        node_raw = str(m.group("node") or "").strip()
        start_raw = str(m.group("start") or "").strip()
        dur_raw = str(m.group("dur") or "").strip()
        reason_raw = str(m.group("reason") or "").strip()

        if app_filter and app_raw != app_filter:
            return None
        if stream_filter and stream_filter not in stream_raw:
            return None
        if node_filter and node_raw != node_filter:
            return None
        if keyword_text and keyword_text not in line.lower():
            return None

        # release time from [ts]
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

        try:
            start_iso = start_raw
            if start_iso:
                # start_raw may include 'T' without timezone; keep as-is
                # still attempt parse to validate
                datetime.fromisoformat(start_iso.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception as e:
            logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
            start_iso = start_raw

        try:
            dur_s = int(dur_raw)
        except Exception as e:
            logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
            dur_s = None

        return {
            "ts": dt.isoformat(sep=" "),
            "app": app_raw,
            "stream": stream_raw,
            "node": node_raw,
            "start": start_iso,
            "duration_s": dur_s,
            "reason": reason_raw,
            "raw": line[:800],
        }

    collected: list[dict] = []
    target_end_inclusive = page * page_size
    cur_day = end_date
    while cur_day >= start_date:
        file_path = FSPath(log_dir) / f"stream_idle_{cur_day.strftime('%Y-%m-%d')}.log"
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
                "app": app_filter or None,
                "stream": stream_filter or None,
                "node": node_filter or None,
            },
        },
    }


@router.get("/runtime/timelapse/events")
async def timelapse_events(
    start_at: str | None = None,
    end_at: str | None = None,
    keyword: str | None = None,
    app: str | None = None,
    stream: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    查询 timelapse 结构化截图事件日志：
      [HH:MM:SS.mmm] app=<app> stream=<stream> asset_id=<id> file=<rel_path>
    """
    plugin_id = "timelapse"

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
    app_filter = str(app or "").strip()
    stream_filter = str(stream or "").strip()

    line_re = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+app=(?P<app>\S+)\s+stream=(?P<stream>\S+)\s+asset_id=(?P<asset>\S+)\s+file=(?P<file>.+)$"
    )

    log_dir = "logs/timelapse"

    def _parse_line(line: str, file_date) -> dict | None:
        if not line:
            return None
        m = line_re.match(line.strip())
        if not m:
            return None
        ts_raw = str(m.group("ts") or "").strip()
        app_raw = str(m.group("app") or "").strip()
        stream_raw = str(m.group("stream") or "").strip()
        asset_raw = str(m.group("asset") or "").strip()
        file_raw = str(m.group("file") or "").strip()

        if app_filter and app_raw != app_filter:
            return None
        if stream_filter and stream_filter not in stream_raw:
            return None
        if keyword_text and keyword_text not in line.lower():
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

        return {
            "ts": dt.isoformat(sep=" "),
            "app": app_raw,
            "stream": stream_raw,
            "asset_id": asset_raw,
            "file": file_raw,
            "raw": line[:800],
        }

    collected: list[dict] = []
    target_end_inclusive = page * page_size
    cur_day = end_date
    while cur_day >= start_date:
        file_path = FSPath(log_dir) / f"timelapse_{cur_day.strftime('%Y-%m-%d')}.log"
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
                "app": app_filter or None,
                "stream": stream_filter or None,
            },
        },
    }


@router.get("/runtime/webhook_pusher/events")
async def webhook_pusher_events(
    start_at: str | None = None,
    end_at: str | None = None,
    keyword: str | None = None,
    device: str | None = None,
    status: str | None = None,
    ok: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    查询 webhook_pusher 事件日志：
      [HH:MM:SS.mmm] device=<id> status=<online|offline> ok=true/false [err=<...>]
    """
    plugin_id = "webhook_pusher"

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
    status_filter = str(status or "").strip().lower()

    # ok: 前端可传 true/false 字符串，FastAPI 会尝试转 bool；此处仍做容错
    ok_filter = ok

    line_re = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+device=(?P<device>\S+)\s+status=(?P<status>\S+)\s+ok=(?P<ok>\S+)(?:\s+err=(?P<err>.*))?$"
    )

    log_dir = "logs/webhook_pusher"

    def _parse_line(line: str, file_date) -> dict | None:
        if not line:
            return None
        m = line_re.match(line.strip())
        if not m:
            return None
        ts_raw = str(m.group("ts") or "").strip()
        device_raw = str(m.group("device") or "").strip()
        status_raw = str(m.group("status") or "").strip().lower()
        ok_raw = str(m.group("ok") or "").strip().lower()
        err_raw = str(m.group("err") or "").strip()

        if device_filter and device_raw != device_filter:
            return None
        if status_filter and status_raw != status_filter:
            return None
        if ok_filter is not None:
            ok_bool = ok_raw in {"true", "1", "yes"}
            if ok_bool != bool(ok_filter):
                return None
        if keyword_text and keyword_text not in line.lower():
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

        ok_bool = ok_raw in {"true", "1", "yes"}

        return {
            "ts": dt.isoformat(sep=" "),
            "device": device_raw,
            "status": status_raw,
            "ok": ok_bool,
            "err": err_raw,
            "raw": line[:800],
        }

    collected: list[dict] = []
    target_end_inclusive = page * page_size
    cur_day = end_date
    while cur_day >= start_date:
        file_path = FSPath(log_dir) / f"webhook_pusher_{cur_day.strftime('%Y-%m-%d')}.log"
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
                "status": status_filter or None,
                "ok": ok_filter,
            },
        },
    }


@router.get("/runtime/s3_sync/events")
async def s3_sync_events(
    start_at: str | None = None,
    end_at: str | None = None,
    keyword: str | None = None,
    bucket: str | None = None,
    ok: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    查询 s3_sync 上传事件日志（不落盘 endpoint/密钥）：
      [HH:MM:SS.mmm] bucket=<name> ok=true/false rel=<object_key> size_bytes=<N> | err=<...>
    """
    plugin_id = "s3_sync"

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
    bucket_filter = str(bucket or "").strip()
    ok_filter = ok

    line_ok = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+bucket=(?P<bucket>\S+)\s+ok=(?P<ok>\S+)\s+rel=(?P<rel>\S+)\s+size_bytes=(?P<size>\d+)\s*$"
    )
    line_fail = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+bucket=(?P<bucket>\S+)\s+ok=(?P<ok>\S+)\s+rel=(?P<rel>\S+)\s+err=(?P<err>.*)$"
    )

    log_dir = "logs/s3_sync"

    def _decode_rel(rel_raw: str) -> str:
        return str(rel_raw or "").replace("%20", " ")

    def _parse_line(line: str, file_date) -> dict | None:
        if not line:
            return None
        s = line.strip()
        m = line_ok.match(s) or line_fail.match(s)
        if not m:
            return None
        ts_raw = str(m.group("ts") or "").strip()
        bucket_raw = str(m.group("bucket") or "").strip()
        ok_raw = str(m.group("ok") or "").strip().lower()
        rel_raw = str(m.group("rel") or "").strip()
        rel_decoded = _decode_rel(rel_raw)

        if bucket_filter and bucket_raw != bucket_filter:
            return None
        if ok_filter is not None:
            ok_bool = ok_raw in {"true", "1", "yes"}
            if ok_bool != bool(ok_filter):
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

        ok_bool = ok_raw in {"true", "1", "yes"}
        size_v: int | None = None
        err_raw = ""
        if ok_bool:
            try:
                size_v = int(m.group("size"))
            except Exception as e:
                logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
                size_v = None
        else:
            err_raw = str(m.groupdict().get("err") or "").strip()

        return {
            "ts": dt.isoformat(sep=" "),
            "bucket": bucket_raw,
            "ok": ok_bool,
            "rel": rel_decoded,
            "size_bytes": size_v,
            "err": err_raw,
            "raw": line[:800],
        }

    collected: list[dict] = []
    target_end_inclusive = page * page_size
    cur_day = end_date
    while cur_day >= start_date:
        file_path = FSPath(log_dir) / f"s3_sync_{cur_day.strftime('%Y-%m-%d')}.log"
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
                "bucket": bucket_filter or None,
                "ok": ok_filter,
            },
        },
    }


@router.get("/runtime/ptz_tour/events")
async def ptz_tour_events(
    start_at: str | None = None,
    end_at: str | None = None,
    keyword: str | None = None,
    device: str | None = None,
    channel: str | None = None,
    ok: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    查询 ptz_tour 预置位轮巡下发日志：
      [HH:MM:SS.mmm] device=<gb> channel=<gb> preset=<N> ok=true/false [err=...]
    """
    plugin_id = "ptz_tour"

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
    channel_filter = str(channel or "").strip()
    ok_filter = ok

    line_ok = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+device=(?P<device>\S+)\s+channel=(?P<channel>\S+)\s+preset=(?P<preset>\d+)\s+ok=true\s*$"
    )
    line_fail = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+device=(?P<device>\S+)\s+channel=(?P<channel>\S+)\s+preset=(?P<preset>\d+)\s+ok=false\s+err=(?P<err>.*)$"
    )

    log_dir = "logs/ptz_tour"

    def _decode_token(t: str) -> str:
        return str(t or "").replace("%20", " ")

    def _parse_line(line: str, file_date) -> dict | None:
        if not line:
            return None
        s = line.strip()
        m = line_ok.match(s) or line_fail.match(s)
        if not m:
            return None
        ts_raw = str(m.group("ts") or "").strip()
        device_raw = _decode_token(str(m.group("device") or "").strip())
        channel_raw = _decode_token(str(m.group("channel") or "").strip())
        try:
            preset_v = int(m.group("preset"))
        except Exception as e:
            logger.debug(f"Operation failed, returning default: {e}")  # A-07 中文日志→英文
            return None

        if device_filter and device_raw != device_filter:
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
        err_raw = ""
        if not ok_bool:
            err_raw = str(m.groupdict().get("err") or "").strip()

        return {
            "ts": dt.isoformat(sep=" "),
            "device": device_raw,
            "channel": channel_raw,
            "preset": preset_v,
            "ok": ok_bool,
            "err": err_raw,
            "raw": line[:800],
        }

    collected: list[dict] = []
    target_end_inclusive = page * page_size
    cur_day = end_date
    while cur_day >= start_date:
        file_path = FSPath(log_dir) / f"ptz_tour_{cur_day.strftime('%Y-%m-%d')}.log"
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
                "channel": channel_filter or None,
                "ok": ok_filter,
            },
        },
    }


@router.get("/runtime/auto_record/events")
async def auto_record_events(
    start_at: str | None = None,
    end_at: str | None = None,
    keyword: str | None = None,
    stream: str | None = None,
    op: str | None = None,
    ok: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    查询 auto_record 调用 ZLM 录像接口日志：
      [HH:MM:SS.mmm] op=start_record|stop_record stream=<gb> ok=true/false [err=...]
    """
    plugin_id = "auto_record"

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
    op_raw = str(op or "").strip().lower()
    op_filter = op_raw if op_raw in {"start_record", "stop_record"} else ""
    ok_filter = ok

    line_ok = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+op=(?P<op>start_record|stop_record)\s+stream=(?P<stream>\S+)\s+ok=true\s*$"
    )
    line_fail = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+op=(?P<op>start_record|stop_record)\s+stream=(?P<stream>\S+)\s+ok=false\s+err=(?P<err>.*)$"
    )

    log_dir = "logs/auto_record"

    def _decode_stream(st: str) -> str:
        return str(st or "").replace("%20", " ")

    def _parse_line(line: str, file_date) -> dict | None:
        if not line:
            return None
        s = line.strip()
        m = line_ok.match(s) or line_fail.match(s)
        if not m:
            return None
        ts_raw = str(m.group("ts") or "").strip()
        op_v = str(m.group("op") or "").strip()
        stream_raw = _decode_stream(str(m.group("stream") or "").strip())

        if op_filter and op_v != op_filter:
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
        err_raw = ""
        if not ok_bool:
            err_raw = str(m.groupdict().get("err") or "").strip()

        return {
            "ts": dt.isoformat(sep=" "),
            "op": op_v,
            "stream": stream_raw,
            "ok": ok_bool,
            "err": err_raw,
            "raw": line[:800],
        }

    collected: list[dict] = []
    target_end_inclusive = page * page_size
    cur_day = end_date
    while cur_day >= start_date:
        file_path = FSPath(log_dir) / f"auto_record_{cur_day.strftime('%Y-%m-%d')}.log"
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
                "op": op_filter or None,
                "ok": ok_filter,
            },
        },
    }


@router.get("/runtime/record_schedule_executor/events")
async def record_schedule_executor_events(
    start_at: str | None = None,
    end_at: str | None = None,
    keyword: str | None = None,
    schedule: str | None = None,
    stream: str | None = None,
    evt: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(require_oss_paid_runtime_from_path),
):
    """
    录像计划执行器动作日志：
      [HH:MM:SS.mmm] schedule=<id> stream=<gb> evt=start_ok|start_fail|stop_ok|stop_fail|blocked_stream [err=...]
    """
    plugin_id = "record_schedule_executor"

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
    schedule_filter = str(schedule or "").strip()
    stream_filter = str(stream or "").strip()
    evt_filter = str(evt or "").strip()
    allowed_evt = {"start_ok", "start_fail", "stop_ok", "stop_fail", "blocked_stream"}
    if evt_filter and evt_filter not in allowed_evt:
        evt_filter = ""

    line_simple = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+schedule=(?P<schedule>\S+)\s+stream=(?P<stream>\S+)\s+evt=(?P<evt>start_ok|stop_ok|blocked_stream)\s*$"
    )
    line_err = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s+schedule=(?P<schedule>\S+)\s+stream=(?P<stream>\S+)\s+evt=(?P<evt>start_fail|stop_fail)\s+err=(?P<err>.*)$"
    )

    log_dir = "logs/record_schedule_executor"

    def _dec(x: str) -> str:
        return str(x or "").replace("%20", " ")

    def _parse_line(line: str, file_date) -> dict | None:
        if not line:
            return None
        s = line.strip()
        m = line_simple.match(s) or line_err.match(s)
        if not m:
            return None
        ts_raw = str(m.group("ts") or "").strip()
        sched_raw = _dec(str(m.group("schedule") or "").strip())
        stream_raw = _dec(str(m.group("stream") or "").strip())
        evt_v = str(m.group("evt") or "").strip()

        if schedule_filter and sched_raw != schedule_filter:
            return None
        if stream_filter and stream_raw != stream_filter:
            return None
        if evt_filter and evt_v != evt_filter:
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

        err_raw = str(m.groupdict().get("err") or "").strip() if line_err.match(s) else ""
        ok_bool = evt_v in {"start_ok", "stop_ok"}

        return {
            "ts": dt.isoformat(sep=" "),
            "schedule": sched_raw,
            "stream": stream_raw,
            "evt": evt_v,
            "ok": ok_bool,
            "err": err_raw,
            "raw": line[:800],
        }

    collected: list[dict] = []
    target_end_inclusive = page * page_size
    cur_day = end_date
    while cur_day >= start_date:
        file_path = FSPath(log_dir) / f"record_schedule_executor_{cur_day.strftime('%Y-%m-%d')}.log"
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
                "schedule": schedule_filter or None,
                "stream": stream_filter or None,
                "evt": evt_filter or None,
            },
        },
    }

