from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy import text as sql_text
from app.db.session import get_db
from app.api import deps
from app.models.user import User
from app.models.system_setting import SystemSetting
from app.core.config import settings
from app.core.db_compat import normalize_db_type, run_compat_checks, vendor_hint
from app.services.auth_audit import safe_auth_audit
from app.sip.trace_events import SIP_TRACE_CONFIG_KEYS, SIP_TRACE_FIELDS, SIP_TRACE_EVENTS
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
import socket
import ipaddress
import json
from typing import Any

router = APIRouter()


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


# 消除重复定义，从_shared模块导入
from app.api.v1.endpoints.stream._shared import _DEFAULT_BOOTSTRAP_TEMPLATES, _DEFAULT_BOOTSTRAP_WEIGHTS


class SystemInfoResponse(BaseModel):
    sip_id: str
    sip_domain: str
    sip_ip: str
    sip_port: int
    sip_password: str | None = None
    version: str
    project_name: str
    sip_auth_skipped: bool = False  # 暴露SIP鉴权跳过状态，便于前端安全提示


class DatabaseConfigPayload(BaseModel):
    database_type: str
    host: str | None = None
    port: int | None = None
    name: str | None = None
    username: str | None = None
    password: str | None = None
    sqlite_path: str | None = None
    sqlalchemy_database_uri: str | None = None


class Gb28181PlayConfigPayload(BaseModel):
    ssrc_policy: str | None = None
    ssrc_retry_on_not_ready: bool | None = None
    ssrc_retry_order: str | None = None
    auto_ensure_embedded_media_node: bool | None = None
    bootstrap_templates: list[dict[str, Any]] | None = None
    bootstrap_learning_weights: dict[str, float] | None = None


@router.get("/sip-trace-events")
async def get_sip_trace_events(
    current_user: User = Depends(deps.require_permission("config.manage"))  # 角色检查→权限码检查
):
    """
    返回 SIP_TRACE 事件字典，供前端/排障脚本展示与筛选。
    """
    return {
        "config": SIP_TRACE_CONFIG_KEYS,
        "fields": SIP_TRACE_FIELDS,
        "events": SIP_TRACE_EVENTS,
    }


def _to_map(items: list[SystemSetting]) -> dict[str, str]:
    return {item.setting_key: item.setting_value for item in items}


def _safe_int(value: str | None, default: int) -> int:
    try:
        return int(value or default)
    except Exception:
        return default


def _parse_json_value(raw: str | None, default: Any) -> Any:
    text = str(raw or "").strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default


def _normalize_bootstrap_templates(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return list(_DEFAULT_BOOTSTRAP_TEMPLATES)
    out: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason") or "").strip()
        mode = str(item.get("mode") or "").strip().upper().replace("-", "_")
        keywords = item.get("keywords")
        if not reason or mode not in {"AUTO", "TCP_PASSIVE", "TCP_ACTIVE"} or not isinstance(keywords, list):
            continue
        clean_keywords = [str(k or "").strip() for k in keywords if str(k or "").strip()]
        if not clean_keywords:
            continue
        out.append({"reason": reason[:64], "mode": mode, "keywords": clean_keywords[:24]})
        if len(out) >= 32:
            break
    if not out:
        return list(_DEFAULT_BOOTSTRAP_TEMPLATES)
    return out


def _normalize_bootstrap_weights(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return dict(_DEFAULT_BOOTSTRAP_WEIGHTS)
    out = dict(_DEFAULT_BOOTSTRAP_WEIGHTS)
    for key in ("policy", "health", "template", "learning"):
        try:
            out[key] = max(0.0, min(5.0, float(value.get(key, out[key]))))
        except Exception:
            out[key] = out[key]
    return out


def _build_uri_from_payload(payload: DatabaseConfigPayload) -> str:
    db_type = normalize_db_type(payload.database_type)
    if payload.sqlalchemy_database_uri:
        return payload.sqlalchemy_database_uri.strip()
    if db_type in {"postgresql", "kingbase"}:
        return (
            f"postgresql+asyncpg://{payload.username}:{payload.password}"
            f"@{payload.host}:{payload.port}/{payload.name}"
        )
    if db_type in {"mysql", "dameng"}:
        return (
            f"mysql+aiomysql://{payload.username}:{payload.password}"
            f"@{payload.host}:{payload.port}/{payload.name}"
        )
    path = payload.sqlite_path or "./pygbsentry.db"
    return f"sqlite+aiosqlite:///{path}"


@router.get("/database")
async def get_database_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("config.manage"))  # 角色检查→权限码检查
):
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.setting_key.like("db.%"))
    )
    values = _to_map(result.scalars().all())
    database_type = normalize_db_type(values.get("db.database_type") or settings.DATABASE_TYPE)
    return {
        "database_type": database_type,
        "host": values.get("db.host") or settings.DATABASE_HOST,
        "port": _safe_int(values.get("db.port"), settings.DATABASE_PORT),
        "name": values.get("db.name") or settings.DATABASE_NAME,
        "username": values.get("db.username") or settings.DATABASE_USER,
        "password": values.get("db.password") or "" if current_user.is_superuser else ("******" if values.get("db.password") else ""),  # W-07-02 operator角色掩码数据库密码
        "sqlite_path": values.get("db.sqlite_path") or settings.DATABASE_SQLITE_PATH,
        "sqlalchemy_database_uri": values.get("db.sqlalchemy_database_uri") or ""
    }


@router.post("/database/test")
async def test_database_config(
    payload: DatabaseConfigPayload,
    current_user: User = Depends(deps.require_permission("config.manage"))  # 角色检查→权限码检查
):
    uri = _build_uri_from_payload(payload)
    db_type = normalize_db_type(payload.database_type)
    try:
        test_engine = create_async_engine(uri, echo=False, pool_pre_ping=True)
        async with test_engine.connect() as conn:
            await conn.execute(sql_text("SELECT 1"))
            compat_report = await run_compat_checks(conn, db_type)
        await test_engine.dispose()
    except Exception as e:
        detail = f"数据库连接失败: {e}"
        db_vendor_hint = vendor_hint(db_type)
        if db_vendor_hint:
            detail += f"；{db_vendor_hint}"
        raise HTTPException(status_code=400, detail=detail)
    parsed = make_url(uri)
    db_vendor_hint = vendor_hint(db_type)
    return {
        "ok": True,
        "dialect": parsed.drivername,
        "database": parsed.database,
        "compatibility": compat_report,
        "vendor_hint": db_vendor_hint,
    }


@router.put("/database")
async def save_database_config(
    payload: DatabaseConfigPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("config.manage"))  # 角色检查→权限码检查
):
    uri = _build_uri_from_payload(payload)
    values = {
        "db.database_type": normalize_db_type(payload.database_type),
        "db.host": payload.host or "",
        "db.port": str(payload.port or 0),
        "db.name": payload.name or "",
        "db.username": payload.username or "",
        "db.password": payload.password or "",
        "db.sqlite_path": payload.sqlite_path or "",
        "db.sqlalchemy_database_uri": payload.sqlalchemy_database_uri or uri,
    }
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.setting_key.in_(list(values.keys())))
    )
    existing = {item.setting_key: item for item in result.scalars().all()}
    for key, value in values.items():
        if key in existing:
            existing[key].setting_value = value
        else:
            db.add(SystemSetting(setting_key=key, setting_value=value))
    await db.commit()
    dt = normalize_db_type(payload.database_type)
    host_part = (payload.host or "").strip().replace(";", ".")[:120]
    await safe_auth_audit(
        db,
        module="system_config",
        action="save_database",
        source="system_settings",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"database_type={dt}; host={host_part}",
    )
    return {
        "status": "ok",
        "message": "Database config saved, restart backend to take effect"  # i18n
    }


def _get_real_ip() -> str:
    try:
        hostname = socket.gethostname()
        ip_list = socket.getaddrinfo(hostname, None)
        for addr_info in ip_list:
            ip = addr_info[4][0]
            if not ip.startswith('127.') and not ip.startswith('::1') and ':' not in ip:
                return ip
        return '127.0.0.1'
    except Exception:
        return '127.0.0.1'

def _is_ipv4(value: str) -> bool:
    try:
        ipaddress.IPv4Address(value)
        return True
    except Exception:
        return False


def _is_public_ipv4(value: str) -> bool:
    try:
        ip = ipaddress.IPv4Address(value)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified)
    except Exception:
        return False


def _resolve_to_ipv4(hostname: str) -> str | None:
    try:
        ip = socket.gethostbyname(hostname)
        return ip if _is_ipv4(ip) else None
    except Exception:
        return None


@router.get("/system-info", response_model=SystemInfoResponse)
async def get_system_info(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("config.manage"))  # 角色检查→权限码检查
):
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.setting_key.like("sip.%"))
    )
    values = _to_map(result.scalars().all())

    sip_id = values.get("sip.sip_id") or settings.SIP_ID
    sip_domain = values.get("sip.sip_domain") or settings.SIP_DOMAIN
    sip_ip = values.get("sip.sip_ip") or settings.SIP_IP
    sip_port = _safe_int(values.get("sip.sip_port"), settings.SIP_PORT)
    sip_password = values.get("sip.password") or settings.SIP_DEFAULT_PASSWORD

    if sip_ip in ("0.0.0.0", "::", "127.0.0.1", "localhost", ""):
        host = request.headers.get("host", "")
        if host:
            if ":" in host:
                candidate = host.split(":")[0]
            else:
                candidate = host
            candidate = (candidate or "").strip()
            # 期望展示“IP”：优先公网 IP；无公网则展示内网 IP。
            # - candidate 若本身是 IPv4：直接使用
            # - candidate 若是域名：解析为 IPv4 后使用
            # - 最终无法得到公网 IP 时，回退为本机内网 IP
            if candidate and not candidate.startswith("localhost"):
                if _is_ipv4(candidate):
                    sip_ip = candidate
                else:
                    resolved = _resolve_to_ipv4(candidate)
                    if resolved:
                        sip_ip = resolved
                    else:
                        sip_ip = _get_real_ip()
            else:
                sip_ip = _get_real_ip()
        else:
            sip_ip = _get_real_ip()

    # 若得到的仍是非公网（例如域名解析到内网/回环），统一回退内网 IP
    if not _is_public_ipv4(sip_ip):
        sip_ip = _get_real_ip()

    return {
        "sip_id": sip_id,
        "sip_domain": sip_domain,
        "sip_ip": sip_ip,
        "sip_port": sip_port,
        "sip_password": sip_password if current_user.is_superuser else ("******" if sip_password else ""),  # W-07-03 operator角色掩码SIP密码
        "version": settings.PROJECT_VERSION,
        "project_name": settings.PROJECT_NAME,
        "sip_auth_skipped": not bool(settings.SIP_DEFAULT_PASSWORD) if current_user.is_superuser else False,  # W45 SIP鉴权跳过状态仅管理员可见
    }


@router.get("/info", response_model=SystemInfoResponse)
async def get_system_info_alias(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("config.manage")),
):
    """Alias for /system-info to support /system/info frontend requests."""
    return await get_system_info(request=request, db=db, current_user=current_user)


@router.get("/gb28181/play-config")
async def get_gb28181_play_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("config.manage"))  # 角色检查→权限码检查
):
    keys = [
        "gb28181.ssrc_policy",
        "gb28181.ssrc_retry_on_not_ready",
        "gb28181.ssrc_retry_order",
        "gb28181.auto_ensure_embedded_media_node",
        "gb28181.bootstrap_templates",
        "gb28181.bootstrap_learning_weights",
    ]
    result = await db.execute(select(SystemSetting).where(SystemSetting.setting_key.in_(keys)))
    values = _to_map(result.scalars().all())
    bootstrap_templates = _normalize_bootstrap_templates(
        _parse_json_value(values.get("gb28181.bootstrap_templates"), list(_DEFAULT_BOOTSTRAP_TEMPLATES))
    )
    bootstrap_learning_weights = _normalize_bootstrap_weights(
        _parse_json_value(values.get("gb28181.bootstrap_learning_weights"), dict(_DEFAULT_BOOTSTRAP_WEIGHTS))
    )
    return {
        "ssrc_policy": values.get("gb28181.ssrc_policy") or getattr(settings, "GB28181_SSRC_POLICY", "adaptive"),
        "ssrc_retry_on_not_ready": (values.get("gb28181.ssrc_retry_on_not_ready") or "").strip().lower() in {"1", "true", "yes", "on"} if "gb28181.ssrc_retry_on_not_ready" in values else bool(getattr(settings, "GB28181_SSRC_RETRY_ON_NOT_READY", True)),
        "ssrc_retry_order": values.get("gb28181.ssrc_retry_order") or getattr(settings, "GB28181_SSRC_RETRY_ORDER", "strict,off"),
        "auto_ensure_embedded_media_node": (values.get("gb28181.auto_ensure_embedded_media_node") or "").strip().lower() in {"1", "true", "yes", "on"} if "gb28181.auto_ensure_embedded_media_node" in values else bool(getattr(settings, "GB28181_AUTO_ENSURE_EMBEDDED_MEDIA_NODE", True)),
        "bootstrap_templates": bootstrap_templates,
        "bootstrap_learning_weights": bootstrap_learning_weights,
    }


@router.put("/gb28181/play-config")
async def save_gb28181_play_config(
    payload: Gb28181PlayConfigPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("config.manage"))  # 角色检查→权限码检查
):
    values: dict[str, str] = {}
    if payload.ssrc_policy is not None:
        values["gb28181.ssrc_policy"] = str(payload.ssrc_policy or "").strip()
    if payload.ssrc_retry_on_not_ready is not None:
        values["gb28181.ssrc_retry_on_not_ready"] = "1" if bool(payload.ssrc_retry_on_not_ready) else "0"
    if payload.ssrc_retry_order is not None:
        values["gb28181.ssrc_retry_order"] = str(payload.ssrc_retry_order or "").strip()
    if payload.auto_ensure_embedded_media_node is not None:
        values["gb28181.auto_ensure_embedded_media_node"] = "1" if bool(payload.auto_ensure_embedded_media_node) else "0"
    if payload.bootstrap_templates is not None:
        normalized_templates = _normalize_bootstrap_templates(payload.bootstrap_templates)
        serialized_templates = json.dumps(normalized_templates, ensure_ascii=False, separators=(",", ":"))
        if len(serialized_templates) > 1900:
            await safe_auth_audit(
                db,
                module="system_config",
                action="save_gb28181_play_config",
                source="system_settings",
                operator=current_user.username or "unknown",
                result="failed",
                tenant_id=_audit_tid(current_user),
                status_code=400,
                detail="bootstrap_templates_too_long",
            )
            raise HTTPException(status_code=400, detail="bootstrap_templates config too long")
        values["gb28181.bootstrap_templates"] = serialized_templates
    if payload.bootstrap_learning_weights is not None:
        normalized_weights = _normalize_bootstrap_weights(payload.bootstrap_learning_weights)
        values["gb28181.bootstrap_learning_weights"] = json.dumps(normalized_weights, ensure_ascii=False, separators=(",", ":"))
    if not values:
        return {"status": "ok"}
    result = await db.execute(select(SystemSetting).where(SystemSetting.setting_key.in_(list(values.keys()))))
    existing = {item.setting_key: item for item in result.scalars().all()}
    for key, value in values.items():
        if key in existing:
            existing[key].setting_value = value
        else:
            db.add(SystemSetting(setting_key=key, setting_value=value))
    await db.commit()
    await safe_auth_audit(
        db,
        module="system_config",
        action="save_gb28181_play_config",
        source="system_settings",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"keys={','.join(sorted(values.keys()))}",
    )
    return {"status": "ok"}


@router.get("/gb28181/learning-state")
async def get_gb28181_learning_state(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("config.manage"))  # 角色检查→权限码检查
):
    """可视化学习状态：返回各画像当前的成功率评分与原始统计"""
    key = "gb28181.bootstrap_learning_state"
    result = await db.execute(select(SystemSetting).where(SystemSetting.setting_key == key))
    item = result.scalars().first()
    state = _parse_json_value(item.setting_value if item else None, {"profiles": {}})
    profiles = state.get("profiles") or {}

    report = []
    for p_key, data in profiles.items():
        modes = {}
        for m in ("UDP", "TCP_PASSIVE", "TCP_ACTIVE"):
            stat = data.get(m) or {"s": 0, "f": 0}
            s = int(stat.get("s") or 0)
            f = int(stat.get("f") or 0)
            # 贝叶斯平滑评分
            score = (float(s) + 1.0) / (float(s + f) + 2.0)
            modes[m] = {
                "success": s,
                "fail": f,
                "score": round(score, 4),
                "preference": "high" if score > 0.6 else ("low" if score < 0.4 else "neutral")
            }
        report.append({
            "profile": p_key,
            "updated_at": data.get("updated_at"),
            "modes": modes
        })

    return {"profiles": report}


@router.delete("/gb28181/learning-state")
async def reset_gb28181_learning_state(
    profile_key: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("config.manage"))  # 角色检查→权限码检查
):
    """手动清理学习状态：支持全量重置或按画像重置数据"""
    key = "gb28181.bootstrap_learning_state"
    result = await db.execute(select(SystemSetting).where(SystemSetting.setting_key == key))
    item = result.scalars().first()
    if not item:
        return {"status": "ok", "message": "no_state_to_reset"}

    if not profile_key:
        # 全量重置
        item.setting_value = json.dumps({"profiles": {}})
    else:
        # 按画像重置
        state = _parse_json_value(item.setting_value, {"profiles": {}})
        profiles = state.get("profiles") or {}
        if profile_key in profiles:
            profiles.pop(profile_key)
            item.setting_value = json.dumps(state, ensure_ascii=False, separators=(",", ":"))

    await db.commit()
    pk = (profile_key or "").strip().replace(";", ".")[:120]
    scope = "all" if not profile_key else "profile"
    await safe_auth_audit(
        db,
        module="system_config",
        action="reset_gb28181_learning",
        source="system_settings",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"scope={scope}; profile_key={pk}",
    )
    return {"status": "ok"}
