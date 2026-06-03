from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.core.config import settings
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.asset_stream_health import AssetStreamHealth
from app.models.asset_stream_policy import AssetStreamPolicy
from app.models.record import Record
from app.models.user import User
from app.api import deps
import app.sip.invite as sip_invite_module
from app.services.stream_strategy import calculate_failure_rate, normalize_stream_mode, recommend_stream_mode
from pydantic import BaseModel
from typing import Optional, List, Literal
from datetime import datetime, timezone
from loguru import logger

router = APIRouter()


@router.get("/readiness")
async def readiness_probe():
    """K8s/Docker readiness probe: returns 503 if any critical component is degraded."""
    from app.services.health_service import health_service
    if not health_service.is_ready:
        return Response(
            content='{"status":"degraded","reasons":' + str(health_service.degraded_reasons).replace("'", '"') + '}',
            status_code=503,
            media_type="application/json",
        )
    return {"status": "ready"}


@router.get("/liveness")
async def liveness_probe():
    """K8s/Docker liveness probe: returns 200 if the process is alive."""
    return {"status": "alive"}


class DeviceHealth(BaseModel):
    device_id: str
    device_name: str
    last_mode: Optional[str] = None
    last_status_code: Optional[int] = None
    success_total: int = 0
    fail_total: int = 0
    consecutive_failures: int = 0
    auto_switch_count: int = 0
    failure_rate: float = 0
    current_policy_mode: str = "GLOBAL"
    recommended_mode: str = "UDP"
    recommend_reason: str = ""
    risk_level: str = "low"
    updated_at: Optional[datetime] = None
    signal_quality: Optional[str] = None  # good / normal / poor，由 failure_rate 与在线状态推导
    storage_status: Optional[str] = None  # normal / warning / unknown，由录像覆盖情况推导

class ApplyRecommendationsRequest(BaseModel):
    device_ids: List[str] = []
    risk_level: Optional[Literal["low", "medium", "high"]] = None
    min_failure_rate: Optional[float] = None
    only_diff: bool = True
    dry_run: bool = False

class ApplyResult(BaseModel):
    device_id: str
    previous_mode: str
    recommended_mode: str
    would_apply: bool
    applied: bool
    reason: str

class ApplyRecommendationsResponse(BaseModel):
    total: int
    matched: int
    would_apply: int
    applied: int
    results: List[ApplyResult]

class DailyHealthSummary(BaseModel):
    generated_at: datetime
    total_devices: int
    high_risk: int
    medium_risk: int
    low_risk: int
    would_apply: int
    top_risky: List[DeviceHealth]

def _signal_quality_from_rate(failure_rate: float, is_online: bool) -> str:
    if not is_online:
        return "unknown"
    if failure_rate <= 0.1:
        return "good"
    if failure_rate <= 0.3:
        return "normal"
    return "poor"


def _percentile(values: List[float], p: float) -> float:
    arr = [float(x) for x in values if x is not None]
    if not arr:
        return 0.0
    arr.sort()
    if len(arr) == 1:
        return float(arr[0])
    pp = max(0.0, min(1.0, float(p)))
    idx = int(round((len(arr) - 1) * pp))
    idx = max(0, min(len(arr) - 1, idx))
    return float(arr[idx])


def _build_device_health(
    asset: Asset,
    health: Optional[AssetStreamHealth],
    policy_mode_value: str,
    record_count_for_device: int = 0,
    channel_count_for_device: int = 0,
) -> DeviceHealth:
    success_total = health.success_total if health else 0
    fail_total = health.fail_total if health else 0
    failure_rate = calculate_failure_rate(success_total, fail_total)
    current_policy_mode = normalize_stream_mode(policy_mode_value, default_mode="GLOBAL", allow_auto=True)
    default_mode = normalize_stream_mode(current_policy_mode if current_policy_mode != "GLOBAL" else "UDP")
    recommended_mode, recommend_reason, risk_level = recommend_stream_mode(
        last_mode=health.last_mode if health else None,
        current_mode=default_mode,
        success_total=success_total,
        fail_total=fail_total,
        consecutive_failures=health.consecutive_failures if health else 0,
        auto_switch_count=health.auto_switch_count if health else 0,
    )
    signal_quality = _signal_quality_from_rate(failure_rate, is_online=(asset.status == 1))
    if channel_count_for_device == 0:
        storage_status = "unknown"
    elif record_count_for_device >= channel_count_for_device:
        storage_status = "normal"
    elif record_count_for_device > 0:
        storage_status = "normal"
    else:
        storage_status = "warning"
    return DeviceHealth(
        device_id=asset.gb_id,
        device_name=asset.name,
        last_mode=health.last_mode if health else None,
        last_status_code=health.last_status_code if health else None,
        success_total=success_total,
        fail_total=fail_total,
        consecutive_failures=health.consecutive_failures if health else 0,
        auto_switch_count=health.auto_switch_count if health else 0,
        failure_rate=failure_rate,
        current_policy_mode=current_policy_mode,
        recommended_mode=recommended_mode,
        recommend_reason=recommend_reason,
        risk_level=risk_level,
        updated_at=health.updated_at if health else None,
        signal_quality=signal_quality,
        storage_status=storage_status,
    )

@router.get("/overview")
async def get_ops_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """运维概览：设备数、在线数、通道数、在线率、录像条数，用于 Dashboard 与报表。"""
    tenant_id = None if current_user.is_superuser else (current_user.tenant_id or "default")
    asset_stmt = select(Asset)
    if tenant_id:
        asset_stmt = asset_stmt.where(Asset.tenant_id == tenant_id)
    assets = (await db.execute(asset_stmt)).scalars().all()
    device_total = len(assets)
    device_online = sum(1 for a in assets if a.status == 1)
    asset_ids = [a.id for a in assets]
    res_count = (await db.execute(select(Resource).where(Resource.asset_id.in_(asset_ids)))).scalars().all() if asset_ids else []
    channel_total = len(res_count)
    channel_online = sum(1 for r in res_count if r.status == 1)
    online_rate_pct = round(100.0 * device_online / device_total, 1) if device_total else 0
    record_result = await db.execute(select(Record))
    records = record_result.scalars().all()
    record_count = len(records)
    # 录像完整率：有录像记录的通道数 / 通道总数（通道总数可为 0）
    resource_ids_with_record = {r.resource_id for r in records}
    channels_with_record = sum(1 for r in res_count if r.id in resource_ids_with_record)
    record_completeness_pct = round(100.0 * channels_with_record / channel_total, 1) if channel_total else 0
    sip_rate_limit = {}
    with_rate_metrics = bool(getattr(settings, "SIP_INVITE_RATE_LIMIT_PER_DEVICE", 0) or getattr(settings, "SIP_INVITE_RATE_LIMIT_PER_TENANT", 0))
    if with_rate_metrics and getattr(sip_invite_module, "get_invite_rate_limit_metrics", None):
        try:
            sip_rate_limit = sip_invite_module.get_invite_rate_limit_metrics()
        except Exception as e:
            logger.debug(f"操作失败,返回默认值: {e}")
            sip_rate_limit = {}
    return {
        "device_total": device_total,
        "device_online": device_online,
        "channel_total": channel_total,
        "channel_online": channel_online,
        "online_rate_pct": online_rate_pct,
        "record_count": record_count,
        "channels_with_record": channels_with_record,
        "record_completeness_pct": record_completeness_pct,
        "sip_rate_limit": sip_rate_limit,
    }


@router.get("/sip-rate-limit")
async def get_sip_rate_limit_metrics(
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    metrics = {}
    if getattr(sip_invite_module, "get_invite_rate_limit_metrics", None):
        try:
            metrics = sip_invite_module.get_invite_rate_limit_metrics()
        except Exception as e:
            logger.debug(f"操作失败,返回默认值: {e}")
            metrics = {}
    return {"status": "ok", "metrics": metrics}


@router.get("/capacity-baseline")
async def get_capacity_baseline(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    tenant_id = None if current_user.is_superuser else (current_user.tenant_id or "default")
    items = await _load_all_device_health(db, tenant_id=tenant_id)
    total = int(len(items))
    high_risk = int(sum(1 for x in items if x.risk_level == "high"))
    unstable = int(sum(1 for x in items if x.consecutive_failures > 0))
    failure_rates = [float(x.failure_rate or 0.0) for x in items]
    avg_failure_rate = round((sum(failure_rates) / total) if total > 0 else 0.0, 2)
    p95_failure_rate = round(_percentile(failure_rates, 0.95), 2)
    high_risk_ratio = round((high_risk / total) if total > 0 else 0.0, 4)
    unstable_ratio = round((unstable / total) if total > 0 else 0.0, 4)
    sip_metrics = {}
    if getattr(sip_invite_module, "get_invite_rate_limit_metrics", None):
        try:
            sip_metrics = sip_invite_module.get_invite_rate_limit_metrics()
        except Exception as e:
            logger.debug(f"操作失败,返回默认值: {e}")
            sip_metrics = {}
    health_level = "green"
    if high_risk_ratio >= 0.3 or unstable_ratio >= 0.35 or p95_failure_rate >= 60:
        health_level = "red"
    elif high_risk_ratio >= 0.15 or unstable_ratio >= 0.2 or p95_failure_rate >= 35:
        health_level = "yellow"
    return {
        "tenant_scope": tenant_id or "all",
        "total_devices": total,
        "high_risk_devices": high_risk,
        "unstable_devices": unstable,
        "avg_failure_rate_pct": avg_failure_rate,
        "p95_failure_rate_pct": p95_failure_rate,
        "high_risk_ratio": high_risk_ratio,
        "unstable_ratio": unstable_ratio,
        "health_level": health_level,
        "thresholds": {"high_risk_ratio_warn": 0.15, "high_risk_ratio_crit": 0.30, "unstable_ratio_warn": 0.20, "unstable_ratio_crit": 0.35},
        "sip_rate_limit": sip_metrics,
    }


@router.get("/tuning-recommendations")
async def get_tuning_recommendations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    tenant_id = None if current_user.is_superuser else (current_user.tenant_id or "default")
    items = await _load_all_device_health(db, tenant_id=tenant_id)
    total = int(len(items))
    high_risk_ratio = (sum(1 for x in items if x.risk_level == "high") / total) if total > 0 else 0.0
    unstable_ratio = (sum(1 for x in items if x.consecutive_failures > 0) / total) if total > 0 else 0.0
    profile = "balanced"
    if high_risk_ratio >= 0.3 or unstable_ratio >= 0.35:
        profile = "stability_first"
    elif high_risk_ratio <= 0.05 and unstable_ratio <= 0.1:
        profile = "throughput_first"
    current_snapshot_concurrency = int(getattr(settings, "SNAPSHOT_BATCH_CONCURRENCY", 5) or 5)
    current_snapshot_timeout = float(getattr(settings, "SNAPSHOT_BATCH_ITEM_TIMEOUT_SECONDS", 45.0) or 45.0)
    current_invite_per_device = int(getattr(settings, "SIP_INVITE_RATE_LIMIT_PER_DEVICE", 8) or 8)
    current_invite_per_tenant = int(getattr(settings, "SIP_INVITE_RATE_LIMIT_PER_TENANT", 40) or 40)
    suggested_snapshot_concurrency = current_snapshot_concurrency
    suggested_snapshot_timeout = current_snapshot_timeout
    suggested_invite_per_device = current_invite_per_device
    suggested_invite_per_tenant = current_invite_per_tenant
    reason = "当前稳定性与吞吐平衡，可保持现状"
    if profile == "stability_first":
        suggested_snapshot_concurrency = max(2, current_snapshot_concurrency - 1)
        suggested_snapshot_timeout = min(120.0, current_snapshot_timeout + 10.0)
        suggested_invite_per_device = max(4, current_invite_per_device - 1)
        suggested_invite_per_tenant = max(20, current_invite_per_tenant - 5)
        reason = "高风险/不稳定设备占比偏高，建议收敛并发并放宽超时以提升成功率"
    elif profile == "throughput_first":
        suggested_snapshot_concurrency = min(10, current_snapshot_concurrency + 1)
        suggested_snapshot_timeout = max(20.0, current_snapshot_timeout - 5.0)
        suggested_invite_per_device = min(20, current_invite_per_device + 1)
        suggested_invite_per_tenant = min(120, current_invite_per_tenant + 5)
        reason = "整体稳定，可适度提升吞吐降低等待时间"
    recommendations = [
        {"key": "SNAPSHOT_BATCH_CONCURRENCY", "current": current_snapshot_concurrency, "suggested": suggested_snapshot_concurrency},
        {"key": "SNAPSHOT_BATCH_ITEM_TIMEOUT_SECONDS", "current": current_snapshot_timeout, "suggested": round(suggested_snapshot_timeout, 2)},
        {"key": "SIP_INVITE_RATE_LIMIT_PER_DEVICE", "current": current_invite_per_device, "suggested": suggested_invite_per_device},
        {"key": "SIP_INVITE_RATE_LIMIT_PER_TENANT", "current": current_invite_per_tenant, "suggested": suggested_invite_per_tenant},
    ]
    changed = [x for x in recommendations if str(x.get("current")) != str(x.get("suggested"))]
    return {
        "tenant_scope": tenant_id or "all",
        "profile": profile,
        "reason": reason,
        "high_risk_ratio": round(high_risk_ratio, 4),
        "unstable_ratio": round(unstable_ratio, 4),
        "recommendations": recommendations,
        "changed_count": len(changed),
    }


@router.get("/capacity-threshold-template")
async def get_capacity_threshold_template(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    tenant_id = None if current_user.is_superuser else (current_user.tenant_id or "default")
    items = await _load_all_device_health(db, tenant_id=tenant_id)
    total = int(len(items))
    high_risk = int(sum(1 for x in items if x.risk_level == "high"))
    unstable = int(sum(1 for x in items if x.consecutive_failures > 0))
    high_risk_ratio = (high_risk / total) if total > 0 else 0.0
    unstable_ratio = (unstable / total) if total > 0 else 0.0
    profile = "balanced"
    if total >= 500:
        profile = "large_cluster"
    elif total >= 200:
        profile = "mid_cluster"
    if high_risk_ratio >= 0.3 or unstable_ratio >= 0.35:
        profile = "stability_first"
    alert_template = {
        "high_risk_ratio_warn": 0.15 if profile != "stability_first" else 0.10,
        "high_risk_ratio_crit": 0.30 if profile != "stability_first" else 0.20,
        "unstable_ratio_warn": 0.20 if profile != "stability_first" else 0.15,
        "unstable_ratio_crit": 0.35 if profile != "stability_first" else 0.25,
        "p95_failure_rate_warn": 35 if profile != "stability_first" else 25,
        "p95_failure_rate_crit": 60 if profile != "stability_first" else 45,
    }
    recommended_concurrency = int(getattr(settings, "SNAPSHOT_BATCH_CONCURRENCY", 5) or 5)
    if profile == "large_cluster":
        recommended_concurrency = min(10, max(recommended_concurrency, 7))
    elif profile == "mid_cluster":
        recommended_concurrency = min(8, max(recommended_concurrency, 6))
    elif profile == "stability_first":
        recommended_concurrency = max(3, min(recommended_concurrency, 5))
    p95_target_ms = 4500 if profile in {"large_cluster", "mid_cluster"} else 6000
    return {
        "tenant_scope": tenant_id or "all",
        "profile": profile,
        "fleet_size": total,
        "current": {"high_risk_ratio": round(high_risk_ratio, 4), "unstable_ratio": round(unstable_ratio, 4)},
        "alert_template": alert_template,
        "performance_target": {"snapshot_p95_ms": p95_target_ms, "play_first_frame_p95_ms": 3000},
        "recommended_concurrency": recommended_concurrency,
    }


@router.get("/loadtest-spec")
async def get_loadtest_spec(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    tenant_id = None if current_user.is_superuser else (current_user.tenant_id or "default")
    items = await _load_all_device_health(db, tenant_id=tenant_id)
    total = int(len(items))
    channel_sample = 20 if total <= 100 else (50 if total <= 500 else 100)
    ramp_seconds = 30 if total <= 100 else (60 if total <= 500 else 120)
    return {
        "tenant_scope": tenant_id or "all",
        "fleet_size": total,
        "snapshot_batch_test": {
            "channel_sample": channel_sample,
            "concurrency_levels": [3, 5, 8, 10],
            "iterations_per_level": 3,
            "target_p95_ms": 6000,
            "ramp_seconds": ramp_seconds,
        },
        "play_test": {
            "device_channel_sample": min(30, max(5, total // 10 if total > 0 else 5)),
            "concurrency_levels": [2, 4, 6],
            "target_first_frame_p95_ms": 3000,
        },
    }


async def _load_all_device_health(db: AsyncSession, tenant_id: Optional[str] = None) -> List[DeviceHealth]:
    from sqlalchemy import func
    stmt = select(Asset, AssetStreamHealth).outerjoin(
        AssetStreamHealth, Asset.id == AssetStreamHealth.asset_id
    )
    if tenant_id:
        stmt = stmt.where(Asset.tenant_id == tenant_id)
    result = await db.execute(stmt)
    rows = result.all()
    policy_result = await db.execute(select(AssetStreamPolicy))
    policy_map = {policy.asset_id: policy.stream_mode for policy in policy_result.scalars().all()}
    asset_ids = [asset.id for asset, _ in rows]
    channel_count_stmt = select(Resource.asset_id, func.count(Resource.id)).where(
        Resource.asset_id.in_(asset_ids)
    ).group_by(Resource.asset_id)
    channel_rows = (await db.execute(channel_count_stmt)).all()
    channel_map = {row[0]: row[1] for row in channel_rows}
    record_count_stmt = select(Record.asset_id, func.count(Record.id)).where(
        Record.asset_id.in_(asset_ids)
    ).group_by(Record.asset_id)
    record_rows = (await db.execute(record_count_stmt)).all()
    record_map = {row[0]: row[1] for row in record_rows}
    return [
        _build_device_health(
            asset,
            health,
            policy_map.get(asset.id, "GLOBAL"),
            record_count_for_device=record_map.get(asset.id, 0),
            channel_count_for_device=channel_map.get(asset.id, 0),
        )
        for asset, health in rows
    ]

def _filter_device_health(
    items: List[DeviceHealth],
    risk_level: Optional[str],
    min_failure_rate: float,
    current_policy_mode: Optional[str],
    only_diff: bool,
) -> List[DeviceHealth]:
    result: List[DeviceHealth] = []
    normalized_mode = normalize_stream_mode(current_policy_mode, default_mode="GLOBAL", allow_auto=True) if current_policy_mode else None
    for item in items:
        if risk_level and item.risk_level != risk_level:
            continue
        if item.failure_rate < min_failure_rate:
            continue
        if normalized_mode and item.current_policy_mode != normalized_mode:
            continue
        if only_diff and item.current_policy_mode == item.recommended_mode:
            continue
        result.append(item)
    return result

@router.get("/devices", response_model=List[DeviceHealth])
async def get_devices_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    risk_level: Optional[Literal["low", "medium", "high"]] = None,
    min_failure_rate: float = 0,
    current_policy_mode: Optional[str] = None,
    only_diff: bool = False,
):
    tenant_id = None if current_user.is_superuser else (current_user.tenant_id or "default")
    health_data = await _load_all_device_health(db, tenant_id=tenant_id)
    return _filter_device_health(health_data, risk_level, min_failure_rate, current_policy_mode, only_diff)

@router.get("/report/daily", response_model=DailyHealthSummary)
async def get_daily_report(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    top_limit: int = Query(default=10, ge=1, le=50),
):
    tenant_id = None if current_user.is_superuser else (current_user.tenant_id or "default")
    items = await _load_all_device_health(db, tenant_id=tenant_id)
    sorted_items = sorted(
        items,
        key=lambda item: (item.risk_level == "high", item.failure_rate, item.consecutive_failures),
        reverse=True
    )
    would_apply_count = sum(1 for item in items if item.current_policy_mode != item.recommended_mode)
    return DailyHealthSummary(
        generated_at=datetime.now(timezone.utc),
        total_devices=len(items),
        high_risk=sum(1 for item in items if item.risk_level == "high"),
        medium_risk=sum(1 for item in items if item.risk_level == "medium"),
        low_risk=sum(1 for item in items if item.risk_level == "low"),
        would_apply=would_apply_count,
        top_risky=sorted_items[:top_limit],
    )

@router.get("/report/daily.csv")
async def download_daily_report_csv(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    tenant_id = None if current_user.is_superuser else (current_user.tenant_id or "default")
    items = await _load_all_device_health(db, tenant_id=tenant_id)
    rows = [
        "device_id,device_name,risk_level,current_policy_mode,recommended_mode,failure_rate,consecutive_failures,auto_switch_count,recommend_reason,updated_at"
    ]
    for item in items:
        def esc(value: str) -> str:
            v = str(value or "")
            return '"' + v.replace('"', '""') + '"'
        rows.append(",".join([
            esc(item.device_id),
            esc(item.device_name),
            esc(item.risk_level),
            esc(item.current_policy_mode),
            esc(item.recommended_mode),
            esc(str(item.failure_rate)),
            esc(str(item.consecutive_failures)),
            esc(str(item.auto_switch_count)),
            esc(item.recommend_reason),
            esc(item.updated_at.isoformat() if item.updated_at else ""),
        ]))
    csv_content = "\ufeff" + "\n".join(rows)
    filename = f"health-daily-report-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

@router.post("/apply-recommendations", response_model=ApplyRecommendationsResponse)
async def apply_recommendations(
    payload: ApplyRecommendationsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    stmt = select(Asset, AssetStreamHealth).outerjoin(
        AssetStreamHealth, Asset.id == AssetStreamHealth.asset_id
    )
    result = await db.execute(stmt)
    rows = result.all()
    policy_result = await db.execute(select(AssetStreamPolicy))
    policy_list = policy_result.scalars().all()
    policy_map = {policy.asset_id: policy for policy in policy_list}
    matched = 0
    would_apply = 0
    applied = 0
    results: List[ApplyResult] = []
    device_id_set = set(payload.device_ids or [])
    for asset, health in rows:
        device_item = _build_device_health(asset, health, policy_map.get(asset.id).stream_mode if policy_map.get(asset.id) else "GLOBAL")
        if device_id_set and device_item.device_id not in device_id_set:
            continue
        if payload.risk_level and device_item.risk_level != payload.risk_level:
            continue
        if payload.min_failure_rate is not None and device_item.failure_rate < payload.min_failure_rate:
            continue
        if payload.only_diff and device_item.current_policy_mode == device_item.recommended_mode:
            continue
        matched += 1
        previous_mode = device_item.current_policy_mode
        recommended_mode = device_item.recommended_mode
        reason = device_item.recommend_reason
        should_change = previous_mode != recommended_mode
        if should_change:
            would_apply += 1
        changed = False
        if not payload.dry_run:
            policy = policy_map.get(asset.id)
            if not policy:
                policy = AssetStreamPolicy(asset_id=asset.id, stream_mode=recommended_mode)
                db.add(policy)
                policy_map[asset.id] = policy
                changed = True
            elif policy.stream_mode != recommended_mode:
                policy.stream_mode = recommended_mode
                changed = True
            if changed:
                applied += 1
                logger.info(
                    f"Health recommendation applied by {current_user.username}: "
                    f"device={device_item.device_id}, from={previous_mode}, to={recommended_mode}, risk={device_item.risk_level}"
                )
        results.append(
            ApplyResult(
                device_id=device_item.device_id,
                previous_mode=previous_mode,
                recommended_mode=recommended_mode,
                would_apply=should_change,
                applied=changed and not payload.dry_run,
                reason=reason,
            )
        )
    if not payload.dry_run and applied > 0:
        await db.commit()
    return ApplyRecommendationsResponse(
        total=len(rows),
        matched=matched,
        would_apply=would_apply,
        applied=0 if payload.dry_run else applied,
        results=results,
    )
