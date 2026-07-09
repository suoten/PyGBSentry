"""
报表中心 API。基础列表与摘要由主系统提供占位实现；
完整报表模板、导出、对接由「报表」相关插件扩展。
"""
import io
import math
import os
import hashlib
import json
from typing import Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.models.asset import Asset
from app.models.alarm import Alarm
from app.models.stream_session import StreamSession
from app.models.network_metric import NetworkMetric
from app.core.plugin_manager import plugin_manager
from app.services.config_center_service import config_center_service
# FIX: [2026-07-03] release_center_service 在开源版中不存在，导致 reports 模块加载失败、/reports/* 路由全部 404。
#      根因：企业版服务模块未在开源版中提供。修复：改为可选导入，缺失时 publish 功能降级。 [全栈工程师]
try:
    from app.services.release_center_service import release_center_service
except ImportError:
    release_center_service = None
from app.services.auth_audit import safe_auth_audit
from app.services.stream_quality_monitor import stream_quality_monitor
from loguru import logger

router = APIRouter()

def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


class ReportTemplatePayload(BaseModel):
    id: str
    name: str
    export_formats: list[str] = Field(default_factory=lambda: ["csv"])


class ReportSuiteConfigPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    connector_url: str = ""
    export_formats: list[str] = Field(default_factory=lambda: ["csv", "xlsx"])
    templates: list[ReportTemplatePayload] = Field(default_factory=list)
    publish: bool = False


class CloseoutGovernanceDashboardIngestPayload(BaseModel):
    type: str = "mobile_regression_rotation_closeout_governance_dashboard"
    repository: str = ""
    branch: str = ""
    run_id: str = ""
    generated_at: str = ""
    window_days: int = 14
    policy_env: str = ""
    markdown: str = ""
    dashboard: dict = Field(default_factory=dict)
    idempotency_key: Optional[str] = None
    source: str = "mobile-ci"


def _normalize_report_templates(raw_templates: list[dict] | list[ReportTemplatePayload] | None, fallback_formats: list[str] | None = None) -> list[dict]:
    templates: list[dict] = []
    formats_fallback = fallback_formats or ["csv"]
    for item in raw_templates or []:
        tpl = item if isinstance(item, dict) else item.model_dump()
        rid = str(tpl.get("id") or "").strip()
        name = str(tpl.get("name") or "").strip() or rid
        if not rid:
            continue
        formats = tpl.get("export_formats") or formats_fallback
        if not isinstance(formats, list) or not formats:
            formats = formats_fallback
        templates.append({"id": rid, "name": name, "export_formats": formats})
    return templates


def _closeout_dashboard_store_file() -> Path:
    backend_dir = Path(__file__).resolve().parents[4]
    data_dir = backend_dir / "data" / "reports"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "mobile-regression-rotation-closeout-governance-dashboard-events.json"


def _read_closeout_dashboard_store() -> dict:
    store_file = _closeout_dashboard_store_file()
    if not store_file.exists():
        return {"events": []}
    try:
        return json.loads(store_file.read_text(encoding="utf-8"))
    except Exception:
        return {"events": []}


def _write_closeout_dashboard_store(data: dict) -> None:
    store_file = _closeout_dashboard_store_file()
    store_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dashboard_store_limit() -> int:
    try:
        n = int(os.getenv("MOBILE_CLOSEOUT_DASHBOARD_STORE_MAX_ENTRIES", "2000"))
    except Exception:
        n = 2000
    return max(100, min(20000, n))


def _normalized_dashboard_policy_env(payload: CloseoutGovernanceDashboardIngestPayload) -> str:
    return (payload.policy_env or "").strip().lower() or "unknown"


def _build_dashboard_idempotency_key(
    payload: CloseoutGovernanceDashboardIngestPayload,
    tenant_id: str,
) -> str:
    if payload.idempotency_key and payload.idempotency_key.strip():
        return payload.idempotency_key.strip()
    base = "|".join(
        [
            tenant_id,
            payload.run_id or "",
            payload.generated_at or "",
            _normalized_dashboard_policy_env(payload),
            str(payload.window_days or 14),
        ]
    )
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()
    return f"auto:{digest}"


def _dashboard_closeout_reason(row: dict) -> str:
    return str(
        (((row.get("dashboard") or {}).get("latest") or {}).get("alert") or {}).get("closeout_reason_code")
        or ""
    ).upper()


def _dashboard_reason_code(row: dict) -> str:
    return str(((((row.get("dashboard") or {}).get("latest") or {}).get("alert") or {}).get("reason_code") or "")).upper()


def _dashboard_received_ts(row: dict) -> datetime:
    raw = str(row.get("received_at") or "")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _dashboard_received_day(row: dict) -> str:
    return _dashboard_received_ts(row).strftime("%Y-%m-%d")


async def _get_report_suite_config(db: AsyncSession) -> tuple[dict, str | None]:
    draft = await config_center_service.get_or_create_current_draft(db)
    modules = draft.get("modules") or {}
    plugins = modules.get("plugins") if isinstance(modules, dict) else {}
    if isinstance(plugins, dict):
        cfg = plugins.get("report_suite")
        if isinstance(cfg, dict):
            return cfg, draft.get("draft_id")
    meta = plugin_manager.metadata.get("report_suite") or {}
    cfg = meta.get("config_template") or {}
    return cfg if isinstance(cfg, dict) else {}, draft.get("draft_id")


def _simple_pdf_from_lines(lines: list[str], title: str = "") -> bytes:
    """
    极简 PDF 生成（无三方依赖），适合报表导出（纯文本）。
    使用 Helvetica 字体，按行绘制，超出页高自动分页（不做自动换行）。
    """

    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    page_w, page_h = 595.28, 841.89  # A4 pt
    margin_x, margin_top, margin_bottom = 50.0, 60.0, 60.0
    font_size = 11.0
    leading = 15.0
    usable_h = page_h - margin_top - margin_bottom
    lines_per_page = max(1, int(math.floor(usable_h / leading)))

    all_lines: list[str] = []
    if title:
        all_lines.append(title)
        all_lines.append("")
    all_lines.extend(lines)

    pages: list[str] = []
    for i in range(0, len(all_lines), lines_per_page):
        chunk = all_lines[i : i + lines_per_page]
        y = page_h - margin_top
        ops: list[str] = [
            "BT",
            f"/F1 {font_size:.2f} Tf",
            f"1 0 0 1 {margin_x:.2f} {y:.2f} Tm",
        ]
        first = True
        for ln in chunk:
            if not first:
                ops.append(f"0 -{leading:.2f} Td")
            first = False
            ops.append(f"({_esc(str(ln))}) Tj")
        ops.append("ET")
        pages.append("\n".join(ops))

    objects: list[bytes] = []
    offsets: list[int] = []

    def _current_len() -> int:
        return len(b"%PDF-1.4\n") + sum(len(o) for o in objects)

    def _add(raw: bytes) -> int:
        offsets.append(_current_len())
        objects.append(raw)
        return len(objects)

    # 1: Catalog, 2: Pages, 3: Font
    _add(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    _add(b"2 0 obj\n<< /Type /Pages /Kids [ ] /Count 0 >>\nendobj\n")  # placeholder
    _add(b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    page_ids: list[int] = []
    for content in pages:
        content_bytes = content.encode("utf-8")
        content_obj = (
            f"{len(objects)+1} 0 obj\n<< /Length {len(content_bytes)} >>\nstream\n".encode("utf-8")
            + content_bytes
            + b"\nendstream\nendobj\n"
        )
        content_id = _add(content_obj)
        page_obj = (
            f"{len(objects)+1} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_w:.2f} {page_h:.2f}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>\nendobj\n"
        ).encode("utf-8")
        page_id = _add(page_obj)
        page_ids.append(page_id)

    kids = " ".join([f"{pid} 0 R" for pid in page_ids]).encode("utf-8")
    objects[1] = (
        b"2 0 obj\n<< /Type /Pages /Kids [ "
        + kids
        + f" ] /Count {len(page_ids)} >>\nendobj\n".encode("utf-8")
    )

    pdf = bytearray()
    pdf.extend(b"%PDF-1.4\n")
    for obj in objects:
        pdf.extend(obj)
    xref_start = len(pdf)
    pdf.extend(b"xref\n")
    pdf.extend(f"0 {len(objects)+1}\n".encode("utf-8"))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets:
        pdf.extend(f"{off:010d} 00000 n \n".encode("utf-8"))
    pdf.extend(b"trailer\n")
    pdf.extend(f"<< /Size {len(objects)+1} /Root 1 0 R >>\n".encode("utf-8"))
    pdf.extend(b"startxref\n")
    pdf.extend(f"{xref_start}\n".encode("utf-8"))
    pdf.extend(b"%%EOF")
    return bytes(pdf)


async def _get_summary_stats(db: AsyncSession, current_user: User):
    """统计设备数、今日报警数、当前流数，返回 (stats_dict, items)。"""
    tenant_id = current_user.tenant_id or "default"
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if current_user.is_superuser:
        device_count = (await db.execute(select(func.count(Asset.id)))).scalar() or 0
        alarm_today = (
            await db.execute(select(func.count(Alarm.id)).where(Alarm.time >= today_start))
        ).scalar() or 0
        active_streams = (await db.execute(select(func.count(StreamSession.id)))).scalar() or 0
    else:
        device_count = (
            await db.execute(select(func.count(Asset.id)).where(Asset.tenant_id == tenant_id))
        ).scalar() or 0
        alarm_today = (
            await db.execute(
                select(func.count(Alarm.id)).where(
                    Alarm.tenant_id == tenant_id,
                    Alarm.time >= today_start,
                )
            )
        ).scalar() or 0
        active_streams = (
            await db.execute(
                select(func.count(StreamSession.id))
                .select_from(StreamSession)
                .join(Asset, StreamSession.asset_id == Asset.id)
                .where(Asset.tenant_id == tenant_id)
            )
        ).scalar() or 0
    now_iso = datetime.now(timezone.utc).isoformat()
    stats = {"device_count": device_count, "alarm_today": alarm_today, "active_streams": active_streams}
    items = [
        {"name": "设备总数", "value": device_count, "updated_at": now_iso},
        {"name": "今日报警数", "value": alarm_today, "updated_at": now_iso},
        {"name": "当前流数", "value": active_streams, "updated_at": now_iso},
    ]
    return stats, items


@router.get("/summary")
async def reports_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    报表摘要：返回设备数、今日报警数、当前流数等基础统计；items 供前端展示或由报表插件扩展。
    """
    stats, items = await _get_summary_stats(db, current_user)
    return {
        "items": items,
        "stats": stats,
        "message": "Reports are extended by the report center plugin. Install it to configure templates and data integration here.",  # i18n
    }


@router.get("/report-suite/config")
async def get_report_suite_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("records.view")),  # 角色检查→权限码检查
):
    cfg, draft_id = await _get_report_suite_config(db)
    normalized_formats = cfg.get("export_formats") if isinstance(cfg.get("export_formats"), list) else ["csv", "xlsx"]
    templates = _normalize_report_templates(cfg.get("templates"), normalized_formats)
    return {
        "draft_id": draft_id,
        "config": {
            "enabled": bool(cfg.get("enabled", True)),
            "connector_url": str(cfg.get("connector_url") or ""),
            "export_formats": normalized_formats,
            "templates": templates,
        },
    }


@router.put("/report-suite/config")
async def save_report_suite_config(
    payload: ReportSuiteConfigPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("records.view")),  # 角色检查→权限码检查
):
    try:
        draft = await config_center_service.get_or_create_current_draft(db)
        draft_id = draft.get("draft_id")
        modules = draft.get("modules") or {}
        plugins = modules.get("plugins") if isinstance(modules.get("plugins"), dict) else {}
        report_suite_cfg = {
            "enabled": bool(payload.enabled),
            "connector_url": str(payload.connector_url or "").strip(),
            "export_formats": payload.export_formats or ["csv", "xlsx"],
            "templates": _normalize_report_templates(payload.templates, payload.export_formats or ["csv", "xlsx"]),
        }
        plugins["report_suite"] = report_suite_cfg
        updated = await config_center_service.update_draft_module(
            db=db,
            draft_id=draft_id,
            module_name="plugins",
            payload=plugins,
            operator=current_user.username,
        )
        plugin_manager.metadata["report_suite"] = {"config_template": report_suite_cfg}
        resp = {"status": "ok", "draft_id": updated.get("draft_id"), "config": report_suite_cfg}
        if payload.publish:
            publish_result = await release_center_service.publish(
                db=db,
                draft_id=updated.get("draft_id"),
                operator=current_user.username,
                note="报表中心更新 report_suite 配置",
            )
            resp["publish"] = publish_result
        return resp
    except Exception as e:
        await safe_auth_audit(
            db,
            module="reports",
            action="save_report_suite_config",
            source="report_suite_config",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=500,
            detail="save_report_suite_config_exception",
            extra_summary=f"publish={bool(payload.publish)}; err={str(e)[:200]}",
        )
        raise


@router.get("/list")
async def reports_list(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    报表列表：
    - 默认提供 summary 摘要报表、alarms 报警统计、traffic 流量统计
    - 如安装并启用 report_suite 插件，则合并其 templates 作为额外报表入口
    """
    reports: list[dict] = [
        {
            "id": "summary",
            "name": "平台摘要统计",
            "source": "builtin",
            "export_formats": ["csv", "pdf"],
        },
        {
            "id": "alarms",
            "name": "报警统计报表",
            "source": "builtin",
            "export_formats": ["csv"],
        },
        {
            "id": "traffic",
            "name": "流量趋势报表",
            "source": "builtin",
            "export_formats": ["csv"],
        }
    ]

    cfg, _ = await _get_report_suite_config(db)
    if cfg and cfg.get("enabled"):
        templates = _normalize_report_templates(cfg.get("templates"), cfg.get("export_formats"))
        for tpl in templates:
            reports.append(
                {
                    "id": tpl["id"],
                    "name": tpl["name"],
                    "source": "report_suite",
                    "export_formats": tpl.get("export_formats") or ["csv"],
                }
            )

    return {"reports": reports, "total": len(reports)}


@router.get("/data/alarms")
async def report_data_alarms(
    start_time: str = None,
    end_time: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """报警统计数据：按类型分布"""
    stmt = select(Alarm.alarm_type, func.count(Alarm.id)).group_by(Alarm.alarm_type)

    tenant_id = current_user.tenant_id or "default"
    if not current_user.is_superuser:
        stmt = stmt.where(Alarm.tenant_id == tenant_id)

    if start_time:
        try:
            st = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            stmt = stmt.where(Alarm.time >= st)
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f"start_time date format error: {e}")  # i18n
    if end_time:
        try:
            et = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            stmt = stmt.where(Alarm.time <= et)
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f"end_time date format error: {e}")  # i18n

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {"name": row[0] or "未知类型", "value": row[1]}
        for row in rows
    ]

@router.get("/data/traffic")
async def report_data_traffic(
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = Query(1440, ge=1, le=10000, description="Maximum data points to return"),  # W-07 添加分页限制，防止全量加载
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    流媒体质量数据：
    - active_streams：每个采样点的并发流数
    - zlm_bandwidth_kbps：每个采样点的 ZLM 带宽（Kbps）
    - 采样频率由 network_watchdog 定时任务决定（默认 60s）
    """
    # 默认时间范围：最近 24 小时
    now = datetime.now(timezone.utc)
    if end_time:
        try:
            et = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            end_dt = et.replace(tzinfo=timezone.utc) if et.tzinfo is None else et
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f"end_time date format error: {e}")  # i18n
    else:
        end_dt = now

    if start_time:
        try:
            st = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            start_dt = st.replace(tzinfo=timezone.utc) if st.tzinfo is None else st
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f"start_time date format error: {e}")  # i18n
    else:
        start_dt = end_dt - timedelta(hours=24)

    tenant_id = current_user.tenant_id or "default"
    conditions = [
        NetworkMetric.metric.in_(["active_streams", "zlm_bandwidth_kbps"]),
        NetworkMetric.created_at >= start_dt,
        NetworkMetric.created_at <= end_dt,
    ]
    if not current_user.is_superuser:
        conditions.append(NetworkMetric.tenant_id == tenant_id)

    stmt = (
        select(NetworkMetric)
        .where(*conditions)
        .order_by(NetworkMetric.created_at.asc())
        .limit(limit)  # W-07 添加limit限制，防止全量加载OOM
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    points_streams = []
    points_bandwidth = []
    for row in rows:
        t_str = row.created_at.replace(tzinfo=timezone.utc).isoformat() if row.created_at.tzinfo is None else row.created_at.isoformat()
        if row.metric == "active_streams":
            points_streams.append({"t": t_str, "value": int(row.value)})
        elif row.metric == "zlm_bandwidth_kbps":
            points_bandwidth.append({"t": t_str, "value_kbps": int(row.value)})

    # 汇总统计
    total_streams = sum(p["value"] for p in points_streams)
    total_bandwidth_kbps = sum(p["value_kbps"] for p in points_bandwidth)
    avg_streams = round(total_streams / len(points_streams), 1) if points_streams else 0
    avg_bandwidth_kbps = round(total_bandwidth_kbps / len(points_bandwidth), 1) if points_bandwidth else 0
    max_streams = max((p["value"] for p in points_streams), default=0)
    max_bandwidth_kbps = max((p["value_kbps"] for p in points_bandwidth), default=0)

    return {
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "summary": {
            "avg_streams": avg_streams,
            "max_streams": max_streams,
            "avg_bandwidth_kbps": avg_bandwidth_kbps,
            "max_bandwidth_kbps": max_bandwidth_kbps,
            "sample_count": len(points_streams),
        },
        "streams": points_streams,
        "bandwidth": points_bandwidth,
    }


@router.get("/data/stream-quality")
async def report_data_stream_quality(
    sample_limit: int = Query(30, ge=1, le=120),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ = db  # 保留依赖以复用鉴权链路
    _ = current_user
    snapshot = await stream_quality_monitor.get_dashboard_snapshot(sample_limit)
    sessions = snapshot.get("sessions", []) if isinstance(snapshot, dict) else []

    total = len(sessions)
    level_distribution: dict[str, int] = {}
    score_sum = 0.0
    score_count = 0
    risk_sessions: list[dict] = []
    trend_bucket: dict[str, list[float]] = {}

    for session in sessions:
        latest = session.get("latest") or {}
        level = str(latest.get("health_level") or "unknown").lower()
        level_distribution[level] = int(level_distribution.get(level, 0) + 1)

        score = latest.get("health_score")
        if isinstance(score, (int, float)):
            score_sum += float(score)
            score_count += 1

        if isinstance(score, (int, float)):
            risk_sessions.append(
                {
                    "session_id": session.get("session_id"),
                    "device_id": session.get("device_id"),
                    "channel_id": session.get("channel_id"),
                    "health_score": round(float(score), 2),
                    "health_level": level,
                    "fps": latest.get("fps"),
                    "packet_loss_rate": latest.get("packet_loss_rate"),
                    "buffer_ms": latest.get("buffer_ms"),
                }
            )

        for sample in session.get("samples") or []:
            ts = sample.get("timestamp")
            if not isinstance(ts, (int, float)):
                continue
            minute_key = datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%H:%M")
            sample_score = sample.get("health_score")
            if not isinstance(sample_score, (int, float)):
                continue
            trend_bucket.setdefault(minute_key, []).append(float(sample_score))

    trend = [
        {
            "t": minute,
            "avg_health_score": round(sum(scores) / len(scores), 2),
        }
        for minute, scores in sorted(trend_bucket.items(), key=lambda x: x[0])
        if scores
    ]

    risk_sessions = sorted(risk_sessions, key=lambda x: float(x.get("health_score") or 100))[:10]
    unhealthy = int(level_distribution.get("poor", 0) + level_distribution.get("critical", 0))
    return {
        "summary": {
            "active_sessions": total,
            "avg_health_score": round(score_sum / score_count, 2) if score_count > 0 else 0,
            "unhealthy_sessions": unhealthy,
            "level_distribution": level_distribution,
        },
        "trend": trend,
        "risk_sessions": risk_sessions,
    }


@router.get("/export")
async def reports_export(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    type: str = Query("summary", description="导出类型：summary=摘要统计；alarms=报警统计；traffic=流量统计"),
):
    """
    报表导出：
    - type=summary: 摘要统计 CSV
    - type=alarms: 报警记录 CSV
    - type=traffic: 流量记录 CSV
    """
    if type == "summary":
        _, items = await _get_summary_stats(db, current_user)
        buf = io.StringIO()
        buf.write("指标,数值,导出时间\n")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        for row in items:
            buf.write(f'"{row["name"]}",{row["value"]},{now}\n')
        buf.seek(0)
        filename = f"report_summary_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    elif type == "alarms":
        # Export last 1000 alarms
        stmt = select(Alarm).order_by(Alarm.time.desc()).limit(1000)
        if not current_user.is_superuser:
            stmt = stmt.where(Alarm.tenant_id == (current_user.tenant_id or "default"))
        result = await db.execute(stmt)
        alarms = result.scalars().all()

        buf = io.StringIO()
        buf.write("ID,设备ID,类型,描述,优先级,时间\n")
        for a in alarms:
            t_str = a.time.strftime("%Y-%m-%d %H:%M:%S") if a.time else ""
            desc = (a.description or "").replace('"', '""')
            buf.write(f'"{a.id}","{a.device_id}","{a.alarm_type}","{desc}","{a.priority}","{t_str}"\n')
        buf.seek(0)
        filename = f"report_alarms_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    elif type == "traffic":
        # 从 network_metrics 表查最近 24 小时真实数据
        from app.models.network_metric import NetworkMetric
        start_dt = datetime.now(timezone.utc) - timedelta(hours=24)
        datetime.now(timezone.utc)
        tenant_id = current_user.tenant_id or "default"
        conditions = [
            NetworkMetric.metric.in_(["active_streams", "zlm_bandwidth_kbps"]),
            NetworkMetric.created_at >= start_dt,
        ]
        if not current_user.is_superuser:
            conditions.append(NetworkMetric.tenant_id == tenant_id)
        stmt = (
            select(NetworkMetric)
            .where(*conditions)
            .order_by(NetworkMetric.created_at.asc())
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        # 按时间聚合（去重，同一时间点优先取 streams，其次 bandwidth）
        time_map: dict = {}
        for row in rows:
            t = row.created_at.replace(tzinfo=None) if row.created_at.tzinfo else row.created_at
            t_str = t.strftime("%Y-%m-%d %H:%M:%S")
            if row.metric == "active_streams":
                if t_str not in time_map:
                    time_map[t_str] = {"streams": int(row.value), "bandwidth_kbps": ""}
                else:
                    time_map[t_str]["streams"] = int(row.value)
            elif row.metric == "zlm_bandwidth_kbps":
                if t_str not in time_map:
                    time_map[t_str] = {"streams": "", "bandwidth_kbps": int(row.value)}
                else:
                    time_map[t_str]["bandwidth_kbps"] = int(row.value)

        buf = io.StringIO()
        buf.write("时间,并发流数,带宽(Kbps)\n")
        for t_str, item in sorted(time_map.items()):
            streams = item["streams"]
            bw = item["bandwidth_kbps"]
            buf.write(f"{t_str},{streams},{bw}\n")
        buf.seek(0)
        filename = f"report_traffic_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    cfg, _ = await _get_report_suite_config(db)
    templates = _normalize_report_templates(cfg.get("templates"), cfg.get("export_formats"))
    valid_template_ids = {tpl["id"] for tpl in templates}
    if not (cfg.get("enabled") and cfg.get("connector_url")):
        raise HTTPException(status_code=400, detail="Only built-in summary report export supported, other types require the report_suite plugin")  # i18n
    if type not in valid_template_ids:
        raise HTTPException(status_code=404, detail="Report template not found or not enabled")
    from app.core.http_client import get_http_client

    connector_url = str(cfg.get("connector_url")).strip()
    try:
        params = {"type": type, "tenant_id": current_user.tenant_id or "default", "user_id": current_user.id}
        r = await (await get_http_client()).get(connector_url, params=params, timeout=60)  # 同步requests→异步httpx，避免阻塞事件循环
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Report connector call failed: {e}")
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Report connector returned error: {r.status_code}")
    filename = r.headers.get("Content-Disposition") or f"report_{type}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.bin"
    return StreamingResponse(
        iter([r.content]),
        media_type=r.headers.get("Content-Type") or "application/octet-stream",
        headers={"Content-Disposition": filename},
    )


@router.post("/report-suite/connector-test")
async def test_report_suite_connector(
    connector_url: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("records.view")),  # 角色检查→权限码检查
):
    cfg, _ = await _get_report_suite_config(db)
    target = (connector_url or cfg.get("connector_url") or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="Please configure report_suite.connector_url first")
    from urllib.parse import urlparse
    parsed = urlparse(target)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Only http/https protocol supported")
    if parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or parsed.hostname.endswith(".local"):
        raise HTTPException(status_code=400, detail="Access to local addresses not allowed")
    import ipaddress
    try:
        ipaddress.ip_address(parsed.hostname)
        raise HTTPException(status_code=400, detail="Direct IP address usage not allowed")
    except ValueError as e:
        logger.debug(f"IP地址解析非IP值(预期行为): {e}")
    from app.core.http_client import get_http_client

    try:
        r = await (await get_http_client()).get(target, params={"type": "healthcheck", "tenant_id": current_user.tenant_id or "default"}, timeout=10)  # 同步requests→异步httpx，避免阻塞事件循环
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Connector unavailable: {e}")
    return {
        "ok": r.status_code < 400,
        "status_code": r.status_code,
        "content_type": r.headers.get("Content-Type") or "",
        "connector_url": target,
    }


@router.post("/mobile-regression/closeout-governance-dashboard/ingest")
async def ingest_closeout_governance_dashboard(
    payload: CloseoutGovernanceDashboardIngestPayload,
    current_user: User = Depends(deps.require_permission("records.view")),  # 角色检查→权限码检查
):
    if payload.type != "mobile_regression_rotation_closeout_governance_dashboard":
        raise HTTPException(status_code=400, detail="invalid payload.type")
    tenant_id = current_user.tenant_id or "default"
    now_iso = datetime.now(timezone.utc).isoformat()
    idem_key = _build_dashboard_idempotency_key(payload, tenant_id)
    policy_env = _normalized_dashboard_policy_env(payload)
    generated_at = payload.generated_at or now_iso

    store = _read_closeout_dashboard_store()
    events = store.get("events") if isinstance(store.get("events"), list) else []

    for row in events:
        if (
            str(row.get("tenant_id") or "") == tenant_id
            and str(row.get("idempotency_key") or "") == idem_key
        ):
            return {
                "ok": True,
                "deduped": True,
                "idempotency_key": idem_key,
                "event_id": row.get("event_id"),
                "received_at": row.get("received_at"),
            }

    event = {
        "event_id": hashlib.sha256(f"{tenant_id}|{idem_key}|{now_iso}".encode("utf-8")).hexdigest(),
        "tenant_id": tenant_id,
        "idempotency_key": idem_key,
        "received_at": now_iso,
        "generated_at": generated_at,
        "repository": payload.repository or "",
        "branch": payload.branch or "",
        "run_id": payload.run_id or "",
        "policy_env": policy_env,
        "window_days": int(payload.window_days or 14),
        "source": payload.source or "mobile-ci",
        "dashboard": payload.dashboard or {},
        "markdown": payload.markdown or "",
    }
    events.append(event)
    max_entries = _dashboard_store_limit()
    if len(events) > max_entries:
        events = events[-max_entries:]
    _write_closeout_dashboard_store({"events": events})
    return {
        "ok": True,
        "deduped": False,
        "idempotency_key": idem_key,
        "event_id": event["event_id"],
        "received_at": now_iso,
    }


@router.get("/mobile-regression/closeout-governance-dashboard/latest")
async def get_closeout_governance_dashboard_latest(
    policy_env: Optional[str] = Query(None, description="按环境过滤: prod/canary/dev"),
    current_user: User = Depends(deps.require_permission("records.view")),  # 角色检查→权限码检查
):
    tenant_id = current_user.tenant_id or "default"
    env_filter = (policy_env or "").strip().lower()
    store = _read_closeout_dashboard_store()
    events = store.get("events") if isinstance(store.get("events"), list) else []
    rows = [x for x in events if str(x.get("tenant_id") or "") == tenant_id]
    if env_filter:
        rows = [x for x in rows if str(x.get("policy_env") or "").lower() == env_filter]
    if not rows:
        return {"item": None}
    item = sorted(rows, key=lambda x: str(x.get("received_at") or ""))[-1]
    return {"item": item}


@router.get("/mobile-regression/closeout-governance-dashboard/history")
async def get_closeout_governance_dashboard_history(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    policy_env: Optional[str] = Query(None, description="按环境过滤: prod/canary/dev"),
    reason_code: Optional[str] = Query(None, description="按 closeout reason_code 过滤"),
    current_user: User = Depends(deps.require_permission("records.view")),  # 角色检查→权限码检查
):
    tenant_id = current_user.tenant_id or "default"
    env_filter = (policy_env or "").strip().lower()
    reason_filter = (reason_code or "").strip().upper()
    store = _read_closeout_dashboard_store()
    events = store.get("events") if isinstance(store.get("events"), list) else []
    rows = [x for x in events if str(x.get("tenant_id") or "") == tenant_id]
    if env_filter:
        rows = [x for x in rows if str(x.get("policy_env") or "").lower() == env_filter]
    if reason_filter:
        rows = [
            x
            for x in rows
            if str(
                (((x.get("dashboard") or {}).get("latest") or {}).get("alert") or {}).get("closeout_reason_code")
                or ""
            ).upper()
            == reason_filter
        ]
    rows = sorted(rows, key=lambda x: str(x.get("received_at") or ""), reverse=True)
    total = len(rows)
    page = rows[offset : offset + limit]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": page,
    }


@router.get("/mobile-regression/closeout-governance-dashboard/summary")
async def get_closeout_governance_dashboard_summary(
    days: int = Query(14, ge=1, le=180),
    policy_env: Optional[str] = Query(None, description="按环境过滤: prod/canary/dev"),
    current_user: User = Depends(deps.require_permission("records.view")),  # 角色检查→权限码检查
):
    tenant_id = current_user.tenant_id or "default"
    env_filter = (policy_env or "").strip().lower()
    window_start = datetime.now(timezone.utc) - timedelta(days=days)
    store = _read_closeout_dashboard_store()
    events = store.get("events") if isinstance(store.get("events"), list) else []
    rows = [x for x in events if str(x.get("tenant_id") or "") == tenant_id]
    if env_filter:
        rows = [x for x in rows if str(x.get("policy_env") or "").lower() == env_filter]
    rows = [x for x in rows if _dashboard_received_ts(x) >= window_start]

    by_env: dict[str, int] = {}
    by_reason_code: dict[str, int] = {}
    by_closeout_reason_code: dict[str, int] = {}
    trend_by_day: dict[str, int] = {}

    for row in rows:
        env = str(row.get("policy_env") or "unknown").lower()
        by_env[env] = by_env.get(env, 0) + 1

        reason = _dashboard_reason_code(row) or "UNKNOWN"
        by_reason_code[reason] = by_reason_code.get(reason, 0) + 1

        closeout_reason = _dashboard_closeout_reason(row)
        if closeout_reason:
            by_closeout_reason_code[closeout_reason] = by_closeout_reason_code.get(closeout_reason, 0) + 1

        day_key = _dashboard_received_ts(row).strftime("%Y-%m-%d")
        trend_by_day[day_key] = trend_by_day.get(day_key, 0) + 1

    latest = sorted(rows, key=_dashboard_received_ts)[-1] if rows else None
    return {
        "window_days": days,
        "policy_env_filter": env_filter or None,
        "total": len(rows),
        "by_env": by_env,
        "by_reason_code": by_reason_code,
        "by_closeout_reason_code": by_closeout_reason_code,
        "trend_by_day": trend_by_day,
        "latest": latest,
    }


@router.get("/mobile-regression/closeout-governance-dashboard/drilldown")
async def get_closeout_governance_dashboard_drilldown(
    reason_code: Optional[str] = Query(None, description="按 alerts.reason_code 过滤"),
    closeout_reason_code: Optional[str] = Query(None, description="按 alerts.closeout_reason_code 过滤"),
    policy_env: Optional[str] = Query(None, description="按环境过滤: prod/canary/dev"),
    received_day: Optional[str] = Query(None, description="按接收日期过滤，格式 YYYY-MM-DD"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_dashboard: bool = Query(False, description="是否返回 dashboard 全量体"),
    current_user: User = Depends(deps.require_permission("records.view")),  # 角色检查→权限码检查
):
    tenant_id = current_user.tenant_id or "default"
    env_filter = (policy_env or "").strip().lower()
    reason_filter = (reason_code or "").strip().upper()
    closeout_filter = (closeout_reason_code or "").strip().upper()
    day_filter = (received_day or "").strip()
    if day_filter:
        try:
            datetime.strptime(day_filter, "%Y-%m-%d")
        except Exception:
            raise HTTPException(status_code=400, detail="received_day format must be YYYY-MM-DD")
    store = _read_closeout_dashboard_store()
    events = store.get("events") if isinstance(store.get("events"), list) else []
    rows = [x for x in events if str(x.get("tenant_id") or "") == tenant_id]
    if env_filter:
        rows = [x for x in rows if str(x.get("policy_env") or "").lower() == env_filter]
    if reason_filter:
        rows = [x for x in rows if _dashboard_reason_code(x) == reason_filter]
    if closeout_filter:
        rows = [x for x in rows if _dashboard_closeout_reason(x) == closeout_filter]
    if day_filter:
        rows = [x for x in rows if _dashboard_received_day(x) == day_filter]
    rows = sorted(rows, key=_dashboard_received_ts, reverse=True)
    total = len(rows)
    page = rows[offset : offset + limit]

    items = []
    for row in page:
        item = {
            "event_id": row.get("event_id"),
            "tenant_id": row.get("tenant_id"),
            "idempotency_key": row.get("idempotency_key"),
            "received_at": row.get("received_at"),
            "generated_at": row.get("generated_at"),
            "repository": row.get("repository"),
            "branch": row.get("branch"),
            "run_id": row.get("run_id"),
            "policy_env": row.get("policy_env"),
            "window_days": row.get("window_days"),
            "reason_code": _dashboard_reason_code(row) or "UNKNOWN",
            "closeout_reason_code": _dashboard_closeout_reason(row) or "",
        }
        if include_dashboard:
            item["dashboard"] = row.get("dashboard") or {}
            item["markdown"] = row.get("markdown") or ""
        items.append(item)

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }



@router.get("/export.pdf")
async def reports_export_pdf(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    type: str = Query("summary", description="导出类型：summary=摘要统计"),
):
    """报表导出 PDF。type=summary 时导出当前摘要统计为 PDF。"""
    if type != "summary":
        return {"detail": "Only type=summary supported, other types are extended by report plugins"}  # i18n
    stats, items = await _get_summary_stats(db, current_user)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = []
    lines.append(f"导出时间：{now}")
    lines.append("")
    lines.append(f"设备总数：{stats.get('device_count', 0)}")
    lines.append(f"今日报警数：{stats.get('alarm_today', 0)}")
    lines.append(f"当前流数：{stats.get('active_streams', 0)}")
    lines.append("")
    lines.append("指标 | 数值")
    lines.append("-" * 40)
    for row in items:
        lines.append(f"{row.get('name','')} | {row.get('value','')}")
    pdf_bytes = _simple_pdf_from_lines(lines, title="PyGBSentry 报表摘要")
    filename = f"report_summary_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
