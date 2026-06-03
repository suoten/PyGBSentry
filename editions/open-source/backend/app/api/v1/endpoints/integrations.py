from fastapi import Query, APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_db
from app.api import deps
from app.api.deps import get_or_404
from app.models.user import User
from app.models.media_node import MediaNode
from app.models.access_source import AccessSource
from app.models.system_setting import SystemSetting
from app.models.ffmpeg_cmd import FfmpegCmd
from app.models.resource import Resource
from app.core.config import settings
from app.core.media_nodes_db import (
    get_active_media_node_id,
    get_db_media_node_by_id,
    select_best_db_node,
    cleanup_stale_leases,
    cleanup_invalid_bound_leases,
    ensure_embedded_media_node,
    list_db_media_nodes,
)
from app.services.audit_center_service import audit_center_service
from app.services.auth_audit import safe_auth_audit
from app.services.zlm_stream_control import close_zlm_stream, _get_zlm_client
from app.services.ffmpeg_proxy_manager import ffmpeg_proxy_manager
from app.utils.stream_name import normalize_stream_name
from app.utils.zlm_ssl import validate_and_merge_ssl_pem
from app.models.push_channel import PushChannel
from app.models.media_port_lease import MediaPortLease
import json
from datetime import datetime, timezone
from urllib.parse import urlparse
from loguru import logger

router = APIRouter()


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


class MediaNodePayload(BaseModel):
    ip: str
    public_ip: str | None = None
    stream_ip: str | None = None
    hook_base_url: str | None = None
    hook_ip: str | None = None
    sdp_ip: str | None = None
    http_port: int = 80
    https_port: int = 0
    rtsp_port: int = 554
    rtsps_port: int = 0
    rtmp_port: int = 1935
    rtmps_port: int = 0
    rtp_proxy_port: int = 10000
    rtp_port_mode: str = "single"  # single|range
    rtp_port_range_start: int = 0
    rtp_port_range_end: int = 0
    record_mgr_port: int = 0
    record_file_second: int = 0
    record_sample_ms: int = 0
    protocol_mp4_max_second: int = 0
    secret: str
    is_embedded: bool = False
    auto_config_enabled: bool = False


class ZlmSslCertificatePayload(BaseModel):
    """与 ZLMediaKit 文档一致：可传合并 PEM，或分别传私钥 + 证书链后由服务端拼接。"""

    merged_pem: str | None = None
    cert_pem: str | None = None
    key_pem: str | None = None


class AccessSourcePayload(BaseModel):
    name: str
    protocol: str
    host: str
    port: int = 0
    username: str | None = None
    password: str | None = None
    path: str | None = None
    stream_name: str | None = None
    enabled: bool = True
    gb_enabled: bool = False
    gb_id: str | None = None
    gb_name: str | None = None
    gb_parent_gb_id: str | None = None
    extra: dict = Field(default_factory=dict)


class DesiredStatePayload(BaseModel):
    state: str
    enforce: bool = False


class SourceEnabledPayload(BaseModel):
    enabled: bool


class FfmpegCmdPayload(BaseModel):
    name: str
    cmd_template: str
    enabled: bool = True


@router.get("/ffmpeg_cmd/list")
async def list_ffmpeg_cmds(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    tenant_id = current_user.tenant_id or "default"
    stmt = select(FfmpegCmd)
    if not current_user.is_superuser:
        stmt = stmt.where(FfmpegCmd.tenant_id == tenant_id)
    rows = (await db.execute(stmt)).scalars().all()
    items = []
    for r in rows:
        if str(getattr(r, "enabled", "true") or "true").lower() not in {"true", "1", "yes"}:
            continue
        items.append(
            {
                "id": r.id,
                "name": r.name,
                "cmd_template": r.cmd_template,
            }
        )
    return items


@router.post("/ffmpeg_cmd")
async def create_ffmpeg_cmd(
    payload: FfmpegCmdPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    tenant_id = current_user.tenant_id or "default"
    name = str(payload.name or "").strip()
    cmd_template = str(payload.cmd_template or "").strip()
    if not name or not cmd_template:
        await safe_auth_audit(
            db,
            module="integrations",
            action="create_ffmpeg_cmd",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="name_or_cmd_required",
        )
        raise HTTPException(status_code=400, detail="name/cmd_template is required")
    row = FfmpegCmd(
        tenant_id=tenant_id,
        name=name,
        cmd_template=cmd_template,
        enabled="true" if payload.enabled else "false",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await safe_auth_audit(
        db,
        module="integrations",
        action="create_ffmpeg_cmd",
        source="integrations",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=201,
        detail="ok",
        extra_summary=f"cmd_id={row.id}; name={name[:48]}",
    )
    return {"id": row.id, "name": row.name, "cmd_template": row.cmd_template, "enabled": payload.enabled}


@router.put("/ffmpeg_cmd/{cmd_id}")
async def update_ffmpeg_cmd(
    cmd_id: str,
    payload: FfmpegCmdPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    tenant_id = current_user.tenant_id or "default"
    stmt = select(FfmpegCmd).where(FfmpegCmd.id == cmd_id)
    if not current_user.is_superuser:
        stmt = stmt.where(FfmpegCmd.tenant_id == tenant_id)
    row = (await db.execute(stmt)).scalars().first()
    if not row:
        await safe_auth_audit(
            db,
            module="integrations",
            action="update_ffmpeg_cmd",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"cmd_id={cmd_id}",
        )
        raise HTTPException(status_code=404, detail="ffmpeg_cmd not found")
    name = str(payload.name or "").strip()
    cmd_template = str(payload.cmd_template or "").strip()
    if not name or not cmd_template:
        await safe_auth_audit(
            db,
            module="integrations",
            action="update_ffmpeg_cmd",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="name_or_cmd_required",
            extra_summary=f"cmd_id={cmd_id}",
        )
        raise HTTPException(status_code=400, detail="name/cmd_template is required")
    row.name = name
    row.cmd_template = cmd_template
    row.enabled = "true" if payload.enabled else "false"
    await db.commit()
    await safe_auth_audit(
        db,
        module="integrations",
        action="update_ffmpeg_cmd",
        source="integrations",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"cmd_id={row.id}; name={name[:48]}",
    )
    return {"id": row.id, "name": row.name, "cmd_template": row.cmd_template, "enabled": payload.enabled}


@router.delete("/ffmpeg_cmd/{cmd_id}")
async def delete_ffmpeg_cmd(
    cmd_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    tenant_id = current_user.tenant_id or "default"
    stmt = select(FfmpegCmd).where(FfmpegCmd.id == cmd_id)
    if not current_user.is_superuser:
        stmt = stmt.where(FfmpegCmd.tenant_id == tenant_id)
    row = (await db.execute(stmt)).scalars().first()
    if not row:
        await safe_auth_audit(
            db,
            module="integrations",
            action="delete_ffmpeg_cmd",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"cmd_id={cmd_id}",
        )
        raise HTTPException(status_code=404, detail="ffmpeg_cmd not found")
    await db.delete(row)
    await db.commit()
    await safe_auth_audit(
        db,
        module="integrations",
        action="delete_ffmpeg_cmd",
        source="integrations",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"cmd_id={cmd_id}",
    )
    return {"ok": True}


def _mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}***{value[-2:]}"


def _normalize_protocol(value: str) -> str:
    protocol = (value or "").strip().upper()
    if protocol not in {"GB28181", "ONVIF", "RTSP", "SDK", "RTMP"}:
        raise HTTPException(status_code=400, detail="Unsupported protocol")
    return protocol


def _build_hook_base_url(node: MediaNode | None) -> str:
    """用于 ZLM hook 回调的 base URL（优先 hook_base_url，其次 hook_ip，否则回退全局对外地址）。"""
    def _is_loopback_host(v: str | None) -> bool:
        host = (v or "").strip().lower()
        return host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}

    def _is_loopback_url(v: str | None) -> bool:
        text = (v or "").strip()
        if not text:
            return False
        try:
            return _is_loopback_host(urlparse(text).hostname)
        except Exception as e:
            logger.debug(f"操作失败,返回默认值: {e}")
            return False

    if node:
        hook_base = (getattr(node, "hook_base_url", None) or "").strip()
        if hook_base and not _is_loopback_url(hook_base):
            return hook_base
        hook_ip = (getattr(node, "hook_ip", None) or "").strip()
        if hook_ip and not _is_loopback_host(hook_ip):
            return f"http://{hook_ip}:{settings.BACKEND_PUBLIC_PORT}{settings.API_V1_STR}/hook"
        node_ip = (getattr(node, "ip", None) or "").strip()
        if node_ip and not _is_loopback_host(node_ip):
            return f"http://{node_ip}:{settings.BACKEND_PUBLIC_PORT}{settings.API_V1_STR}/hook"
    global_base = (getattr(settings, "MEDIA_SERVER_HOOK_BASE_URL", None) or "").strip()
    if global_base and not _is_loopback_url(global_base):
        return global_base
    if not _is_loopback_host(getattr(settings, "BACKEND_PUBLIC_HOST", "")):
        return f"http://{settings.BACKEND_PUBLIC_HOST}:{settings.BACKEND_PUBLIC_PORT}{settings.API_V1_STR}/hook"
    media_host = str(getattr(settings, "MEDIA_SERVER_HOST", "") or "").strip()
    if media_host and not _is_loopback_host(media_host):
        return f"http://{media_host}:{settings.BACKEND_PUBLIC_PORT}{settings.API_V1_STR}/hook"
    return f"http://{settings.BACKEND_PUBLIC_HOST}:{settings.BACKEND_PUBLIC_PORT}{settings.API_V1_STR}/hook"


def _build_zlm_hook_urls(base: str, secret: str) -> dict[str, str]:
    s = secret or ""
    return {
        "on_server_started": f"{base}/on_server_started?secret={s}",
        "on_server_keepalive": f"{base}/on_server_keepalive?secret={s}",
        "on_play": f"{base}/on_play?secret={s}",
        "on_publish": f"{base}/on_publish?secret={s}",
        "on_stream_changed": f"{base}/on_stream_changed?secret={s}",
        "on_stream_none_reader": f"{base}/on_stream_none_reader?secret={s}",
        "on_record_mp4": f"{base}/on_record_mp4?secret={s}",
    }


def _build_zlm_config_snippet(node: MediaNode, hook_base_url: str) -> str:
    """
    生成可直接粘贴到 ZLMediaKit config.ini 的关键片段（路 B）。
    内置 ZLM 的 HTTPS 合并 PEM 可在运维中心配置；外置节点仍需在 ZLM 进程侧加载证书（如 -s）。
    """
    secret = (node.secret or "").strip()
    rtp_port = int(getattr(node, "rtp_proxy_port", 0) or 0)
    mode = str(getattr(node, "rtp_port_mode", "single") or "single").lower()
    start = int(getattr(node, "rtp_port_range_start", 0) or 0)
    end = int(getattr(node, "rtp_port_range_end", 0) or 0)
    if mode == "range" and start > 0 and end > 0 and end >= start:
        port_range = f"{start}-{end}"
    else:
        port_range = f"{rtp_port}-{rtp_port}"
    http_port = int(getattr(node, "http_port", 0) or 0)
    https_port = int(getattr(node, "https_port", 0) or 0)
    rtsp_port = int(getattr(node, "rtsp_port", 0) or 0)
    rtsps_port = int(getattr(node, "rtsps_port", 0) or 0)
    rtmp_port = int(getattr(node, "rtmp_port", 0) or 0)
    rtmps_port = int(getattr(node, "rtmps_port", 0) or 0)
    record_file_second = int(getattr(node, "record_file_second", 0) or int(getattr(settings, "ZLM_RECORD_FILE_SECOND", 300) or 300))
    record_sample_ms = int(getattr(node, "record_sample_ms", 0) or int(getattr(settings, "ZLM_RECORD_SAMPLE_MS", 500) or 500))
    protocol_mp4_max_second = int(getattr(node, "protocol_mp4_max_second", 0) or int(getattr(settings, "ZLM_PROTOCOL_MP4_MAX_SECOND", 300) or 300))

    lines = []
    lines.append("[api]")
    lines.append(f"secret={secret}")
    lines.append("")
    lines.append("[http]")
    lines.append(f"port={http_port}")
    if https_port > 0:
        lines.append(f"sslport={https_port}")
    lines.append("")
    lines.append("[rtsp]")
    lines.append(f"port={rtsp_port}")
    if rtsps_port > 0:
        lines.append(f"sslport={rtsps_port}")
    lines.append("")
    lines.append("[rtmp]")
    lines.append(f"port={rtmp_port}")
    if rtmps_port > 0:
        lines.append(f"sslport={rtmps_port}")
    lines.append("")
    lines.append("[rtp_proxy]")
    lines.append(f"port={rtp_port}")
    lines.append(f"port_range={port_range}")
    lines.append("")
    lines.append("[record]")
    lines.append(f"fileSecond={max(30, record_file_second)}")
    lines.append(f"sampleMS={max(100, record_sample_ms)}")
    lines.append("")
    lines.append("[protocol]")
    lines.append(f"mp4_max_second={max(30, protocol_mp4_max_second)}")
    lines.append("")
    lines.append("[hook]")
    lines.append("enable=1")
    for k, v in _build_zlm_hook_urls(hook_base_url, secret).items():
        lines.append(f"{k}={v}")
    lines.append("")
    return "\n".join(lines)


async def _update_source_runtime(db: AsyncSession, source: AccessSource, patch: dict) -> None:
    extra = getattr(source, "extra", None)
    if not isinstance(extra, dict):
        extra = {}
    changed = False
    for k, v in (patch or {}).items():
        key = str(k or "").strip()
        if not key:
            continue
        extra[key] = v
        changed = True
    if not changed:
        return
    source.extra = dict(extra)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("数据库提交失败，已回滚")


async def _check_media_node(node: MediaNode) -> tuple[bool, float]:
    url = f"http://{node.ip}:{node.http_port}/index/api/getServerConfig"
    try:
        sec = (str(node.secret or "").strip() or str(getattr(settings, "MEDIA_SERVER_SECRET", "") or "").strip())
        client = await _get_zlm_client()
        response = await client.get(url, params={"secret": sec}, timeout=3.0)
        if response.status_code >= 400:
            return False, 0.0
        data = response.json()
        code = data.get("code", 1)
        return code == 0, 0.0
    except Exception as e:
        logger.debug(f"操作失败,返回默认值: {e}")
        return False, 0.0


@router.get("/media-nodes")
async def list_media_nodes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"]))
):
    try:
        if bool(getattr(settings, "EMBEDDED_ZLM_ENABLED", True)):
            await ensure_embedded_media_node(db)
    except Exception as e:
        logger.debug(f"非关键操作失败: {e}")
    active_id = await get_active_media_node_id(db)
    result = await db.execute(select(MediaNode))
    nodes = result.scalars().all()
    payload = []
    now = datetime.now(timezone.utc)
    offline_seconds = 120
    try:
        sres = await db.execute(
            select(SystemSetting).where(SystemSetting.setting_key == "media_nodes.offline_seconds")
        )
        setting = sres.scalars().first()
        if setting and setting.setting_value:
            offline_seconds = max(10, min(int(setting.setting_value), 24 * 3600))
    except Exception as e:
        logger.debug(f"操作失败,返回默认值: {e}")
        offline_seconds = 120
    for node in nodes:
        last_seen = getattr(node, "last_seen_at", None)
        computed_online = False
        computed_hook_base = _build_hook_base_url(node)
        try:
            if last_seen:
                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
                computed_online = (now - last_seen).total_seconds() <= offline_seconds
        except Exception as e:
            logger.debug(f"操作失败,返回默认值: {e}")
            computed_online = bool(node.is_online)
        public_host = (getattr(node, "stream_ip", None) or node.public_ip or node.ip or "").strip() or node.ip
        public_http_port = int(getattr(settings, "STREAM_PUBLIC_HTTP_PORT", 0) or 0) or int(node.http_port or 0)
        payload.append({
            "id": node.id,
            "ip": node.ip,
            "public_ip": node.public_ip,
            "is_active": bool(active_id and node.id == active_id),
            "stream_ip": getattr(node, "stream_ip", None),
            "computed_public_host": public_host,
            "computed_public_http_port": public_http_port,
            "hook_base_url": computed_hook_base,
            "hook_base_url_raw": getattr(node, "hook_base_url", None),
            "hook_ip": getattr(node, "hook_ip", None),
            "sdp_ip": getattr(node, "sdp_ip", None),
            "computed_hook_base_url": computed_hook_base,
            "http_port": node.http_port,
            "https_port": getattr(node, "https_port", 0),
            "rtsp_port": node.rtsp_port,
            "rtsps_port": getattr(node, "rtsps_port", 0),
            "rtmp_port": node.rtmp_port,
            "rtmps_port": getattr(node, "rtmps_port", 0),
            "rtp_proxy_port": node.rtp_proxy_port,
            "rtp_port_mode": getattr(node, "rtp_port_mode", "single"),
            "rtp_port_range_start": getattr(node, "rtp_port_range_start", 0),
            "rtp_port_range_end": getattr(node, "rtp_port_range_end", 0),
            "record_mgr_port": getattr(node, "record_mgr_port", 0),
            "record_file_second": getattr(node, "record_file_second", 0),
            "record_sample_ms": getattr(node, "record_sample_ms", 0),
            "protocol_mp4_max_second": getattr(node, "protocol_mp4_max_second", 0),
            "secret": _mask_secret(node.secret),
            "is_online": bool(computed_online),
            "load": node.load,
            "last_seen_at": last_seen.isoformat() if last_seen else None,
            "last_probe_error": getattr(node, "last_probe_error", None),
            "is_embedded": node.is_embedded,
            "auto_config_enabled": getattr(node, "auto_config_enabled", False),
            "zlm_ssl_configured": bool(
                (getattr(node, "zlm_ssl_merged_pem", None) or "").strip()
            ),
        })
    return payload


@router.get("/media-nodes/offline-threshold")
async def get_media_nodes_offline_threshold(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """获取媒体节点离线判定阈值（秒）。"""
    default = 120
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.setting_key == "media_nodes.offline_seconds")
    )
    setting = result.scalars().first()
    value = default
    try:
        if setting and setting.setting_value:
            value = max(10, min(int(setting.setting_value), 24 * 3600))
    except Exception as e:
        logger.debug(f"操作失败,返回默认值: {e}")
        value = default
    return {"offline_seconds": value, "default": default}


class OfflineThresholdPayload(BaseModel):
    offline_seconds: int


@router.put("/media-nodes/offline-threshold")
async def set_media_nodes_offline_threshold(
    payload: OfflineThresholdPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    """设置媒体节点离线判定阈值（秒）。"""
    value = max(10, min(int(payload.offline_seconds or 120), 24 * 3600))
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.setting_key == "media_nodes.offline_seconds")
    )
    setting = result.scalars().first()
    if not setting:
        setting = SystemSetting(setting_key="media_nodes.offline_seconds", setting_value=str(value))
        db.add(setting)
    else:
        setting.setting_value = str(value)
    await db.commit()
    await safe_auth_audit(
        db,
        module="integrations",
        action="set_media_offline_threshold",
        source="integrations",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"offline_seconds={value}",
    )
    return {"offline_seconds": value}


@router.get("/media-nodes/export/media-nodes-json")
async def export_media_nodes_json(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    """
    将运维中心维护的媒体节点导出为 MEDIA_NODES 所需 JSON 结构，便于外置 ZLM / 多节点部署落配置。
    每项字段：
    - id/host/http_port/rtp_port/public_host/public_http_port/secret
    """
    result = await db.execute(select(MediaNode))
    nodes = result.scalars().all()
    out = []
    for node in nodes:
        public_host = (getattr(node, "stream_ip", None) or node.public_ip or node.ip or "").strip() or node.ip
        public_http_port = int(getattr(settings, "STREAM_PUBLIC_HTTP_PORT", 0) or 0) or int(node.http_port or 0)
        out.append(
            {
                "id": node.id,
                "host": node.ip,
                "http_port": int(node.http_port or 0),
                "rtp_port": int(node.rtp_proxy_port or 0),
                "public_host": public_host,
                "public_http_port": public_http_port,
                "secret": node.secret,
            }
        )
    return {"items": out}


@router.get("/media-nodes/export/env")
async def export_media_nodes_env(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    """导出可直接用于环境变量的片段（MEDIA_NODES）。"""
    result = await db.execute(select(MediaNode))
    nodes = result.scalars().all()
    items = []
    for node in nodes:
        public_host = (getattr(node, "stream_ip", None) or node.public_ip or node.ip or "").strip() or node.ip
        public_http_port = int(getattr(settings, "STREAM_PUBLIC_HTTP_PORT", 0) or 0) or int(node.http_port or 0)
        items.append(
            {
                "id": node.id,
                "host": node.ip,
                "http_port": int(node.http_port or 0),
                "rtp_port": int(node.rtp_proxy_port or 0),
                "public_host": public_host,
                "public_http_port": public_http_port,
                "secret": node.secret,
            }
        )
    json_text = json.dumps(items, ensure_ascii=False)
    # Linux shell-friendly（单引号包裹，避免大多数特殊字符；若 secret 包含单引号需用户自行转义）
    env_text = f"export MEDIA_NODES='{json_text}'"
    return {"items": items, "media_nodes_json": json_text, "env": {"MEDIA_NODES": json_text}, "env_text": env_text}


@router.get("/media-nodes/leases")
async def list_media_node_leases(
    node_id: str | None = None,
    only_unbound: bool = False,
    limit: int = Query(200, ge=1, le=10000),  # FIXED
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """
    查看 RTP 端口租约（用于排查端口泄漏/并发占用）。
    - node_id: 仅看某个媒体节点
    - only_unbound: 仅看未绑定 session 的租约（疑似“孤儿租约”）
    """
    safe_limit = max(1, min(int(limit or 200), 1000))
    stmt = select(MediaPortLease).order_by(MediaPortLease.leased_at.desc()).limit(safe_limit)
    if node_id:
        stmt = stmt.where(MediaPortLease.media_server_id == node_id)
    if only_unbound:
        stmt = stmt.where(MediaPortLease.stream_session_id.is_(None))
    result = await db.execute(stmt)
    rows = result.scalars().all()
    items = []
    for r in rows:
        leased_at = getattr(r, "leased_at", None)
        leased_iso = leased_at.isoformat() if leased_at else None
        items.append(
            {
                "id": r.id,
                "media_server_id": r.media_server_id,
                "port": r.port,
                "stream_session_id": r.stream_session_id,
                "leased_at": leased_iso,
            }
        )
    return {"total": len(items), "items": items}


@router.get("/media-nodes/port-pool-status")
async def get_port_pool_status(
    node_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """
    获取媒体节点端口池使用状态，帮助提前预警端口资源耗尽。
    - node_id: 仅看某个媒体节点；不传则返回所有节点
    """
    if node_id:
        nodes = [await get_db_media_node_by_id(db, node_id)]
    else:
        nodes = await list_db_media_nodes(db)

    result: list[dict] = []
    for node in nodes:
        if not node:
            continue

        mode = str(getattr(node, "rtp_port_mode", "single") or "single").lower()
        if mode == "range":
            start = int(getattr(node, "rtp_port_range_start", 0) or 0)
            end = int(getattr(node, "rtp_port_range_end", 0) or 0)
            total = max(0, end - start + 1)
            lease_stmt = (
                select(func.count(MediaPortLease.id))
                .where(MediaPortLease.media_server_id == node.id)
                .where(MediaPortLease.port >= start)
                .where(MediaPortLease.port <= end)
            )
        else:
            total = 1
            lease_stmt = (
                select(func.count(MediaPortLease.id))
                .where(MediaPortLease.media_server_id == node.id)
            )

        lease_result = await db.execute(lease_stmt)
        leased = int(lease_result.scalar() or 0)
        utilization = round((leased / total * 100), 2) if total > 0 else 0.0
        warnings: list[str] = []
        if utilization > 80:
            warnings.append(f"端口使用率超过 80% ({utilization}%)")
        if utilization > 95:
            warnings.append(f"端口即将耗尽！当前使用率 {utilization}%")

        result.append({
            "node_id": node.id,
            "node_name": getattr(node, "name", node.id) or node.id,
            "mode": mode,
            "total_ports": total,
            "leased_ports": leased,
            "available_ports": max(0, total - leased),
            "utilization_rate": utilization,
            "warnings": warnings,
        })

    return {"nodes": result}


class LeaseCleanupPayload(BaseModel):
    max_age_seconds: int = 600
    limit: int = 500
    include_invalid_bound: bool = True


@router.post("/media-nodes/leases/cleanup")
async def cleanup_media_node_leases(
    payload: LeaseCleanupPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    """
    清理未绑定 session 的过期租约（兜底回收端口池）。
    """
    cleaned_orphan = await cleanup_stale_leases(
        db,
        max_age_seconds=int(payload.max_age_seconds or 600),
        limit=int(payload.limit or 500),
    )
    cleaned_invalid_bound = 0
    if bool(getattr(payload, "include_invalid_bound", True)):
        cleaned_invalid_bound = await cleanup_invalid_bound_leases(
            db,
            limit=int(payload.limit or 500),
        )
    cleaned = int(cleaned_orphan or 0) + int(cleaned_invalid_bound or 0)
    await db.commit()
    try:
        operator = (
            getattr(current_user, "username", None)
            or getattr(current_user, "email", None)
            or str(getattr(current_user, "id", "unknown"))
        )
        await audit_center_service.log(
            db=db,
            module="media_nodes",
            action="cleanup_stale_leases",
            operator=str(operator),
            result="success",
            summary=(
                f"cleaned={cleaned}; cleaned_orphan={int(cleaned_orphan or 0)}; "
                f"cleaned_invalid_bound={int(cleaned_invalid_bound or 0)}; "
                f"max_age_seconds={int(payload.max_age_seconds or 600)}; limit={int(payload.limit or 500)}"
            ),
        )
    except Exception as e:
        logger.debug(f"非关键操作失败: {e}")
    return {
        "cleaned": cleaned,
        "cleaned_orphan": int(cleaned_orphan or 0),
        "cleaned_invalid_bound": int(cleaned_invalid_bound or 0),
    }

@router.post("/media-nodes")
async def create_media_node(
    payload: MediaNodePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"]))
):
    node = MediaNode(
        ip=payload.ip.strip(),
        public_ip=(payload.public_ip or "").strip() or None,
        stream_ip=(payload.stream_ip or "").strip() or None,
        hook_base_url=(payload.hook_base_url or "").strip() or None,
        hook_ip=(payload.hook_ip or "").strip() or None,
        sdp_ip=(payload.sdp_ip or "").strip() or None,
        http_port=payload.http_port,
        https_port=payload.https_port,
        rtsp_port=payload.rtsp_port,
        rtsps_port=payload.rtsps_port,
        rtmp_port=payload.rtmp_port,
        rtmps_port=payload.rtmps_port,
        rtp_proxy_port=payload.rtp_proxy_port,
        rtp_port_mode=(payload.rtp_port_mode or "single").strip().lower(),
        rtp_port_range_start=int(payload.rtp_port_range_start or 0),
        rtp_port_range_end=int(payload.rtp_port_range_end or 0),
        record_mgr_port=int(payload.record_mgr_port or 0),
        record_file_second=int(payload.record_file_second or 0),
        record_sample_ms=int(payload.record_sample_ms or 0),
        protocol_mp4_max_second=int(payload.protocol_mp4_max_second or 0),
        secret=payload.secret.strip(),
        is_embedded=payload.is_embedded,
        auto_config_enabled=bool(payload.auto_config_enabled),
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)
    await safe_auth_audit(
        db,
        module="integrations",
        action="create_media_node",
        source="integrations",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=201,
        detail="ok",
        extra_summary=f"node_id={node.id}; ip={payload.ip.strip()[:64]}; embedded={bool(payload.is_embedded)}",
    )
    return {"id": node.id}


@router.put("/media-nodes/{node_id}")
async def update_media_node(
    node_id: str,
    payload: MediaNodePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"]))
):
    result = await db.execute(select(MediaNode).where(MediaNode.id == node_id))
    node = result.scalars().first()
    if not node:
        await safe_auth_audit(
            db,
            module="integrations",
            action="update_media_node",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="node_not_found",
            extra_summary=f"node_id={node_id}",
        )
        raise HTTPException(status_code=404, detail="Media node not found")
    node.ip = payload.ip.strip()
    node.public_ip = (payload.public_ip or "").strip() or None
    node.stream_ip = (payload.stream_ip or "").strip() or None
    node.hook_base_url = (payload.hook_base_url or "").strip() or None
    node.hook_ip = (payload.hook_ip or "").strip() or None
    node.sdp_ip = (payload.sdp_ip or "").strip() or None
    node.http_port = payload.http_port
    node.https_port = payload.https_port
    node.rtsp_port = payload.rtsp_port
    node.rtsps_port = payload.rtsps_port
    node.rtmp_port = payload.rtmp_port
    node.rtmps_port = payload.rtmps_port
    node.rtp_proxy_port = payload.rtp_proxy_port
    node.rtp_port_mode = (payload.rtp_port_mode or "single").strip().lower()
    node.rtp_port_range_start = int(payload.rtp_port_range_start or 0)
    node.rtp_port_range_end = int(payload.rtp_port_range_end or 0)
    node.record_mgr_port = int(payload.record_mgr_port or 0)
    node.record_file_second = int(payload.record_file_second or 0)
    node.record_sample_ms = int(payload.record_sample_ms or 0)
    node.protocol_mp4_max_second = int(payload.protocol_mp4_max_second or 0)
    node.secret = payload.secret.strip()
    node.is_embedded = payload.is_embedded
    node.auto_config_enabled = bool(payload.auto_config_enabled)
    await db.commit()
    await safe_auth_audit(
        db,
        module="integrations",
        action="update_media_node",
        source="integrations",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"node_id={node_id}; ip={payload.ip.strip()[:64]}",
    )
    return {"status": "ok"}


@router.delete("/media-nodes/{node_id}")
async def delete_media_node(
    node_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"]))
):
    result = await db.execute(select(MediaNode).where(MediaNode.id == node_id))
    node = result.scalars().first()
    if not node:
        await safe_auth_audit(
            db,
            module="integrations",
            action="delete_media_node",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="node_not_found",
            extra_summary=f"node_id={node_id}",
        )
        raise HTTPException(status_code=404, detail="Media node not found")
    await db.delete(node)
    await db.commit()
    await safe_auth_audit(
        db,
        module="integrations",
        action="delete_media_node",
        source="integrations",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"node_id={node_id}",
    )
    return {"status": "ok"}


@router.get("/media-nodes/{node_id}/zlm-ssl")
async def get_media_node_zlm_ssl_status(
    node_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """是否已保存合并 PEM（不返回私钥内容）。仅内置节点有意义。"""
    result = await db.execute(select(MediaNode).where(MediaNode.id == node_id))
    node = get_or_404(result, detail="MediaNode not found")  # FIXED: ORM查询结果空值判断
    configured = bool((getattr(node, "zlm_ssl_merged_pem", None) or "").strip())
    return {
        "configured": configured,
        "is_embedded": bool(node.is_embedded),
        "hint": "Certificate is written to the binary directory with -s flag when built-in ZLMediaKit starts; restart backend/media service to apply.",  # FIXED-P3: i18n
    }


@router.put("/media-nodes/{node_id}/zlm-ssl")
async def put_media_node_zlm_ssl(
    node_id: str,
    payload: ZlmSslCertificatePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    result = await db.execute(select(MediaNode).where(MediaNode.id == node_id))
    node = result.scalars().first()
    if not node:
        await safe_auth_audit(
            db,
            module="integrations",
            action="put_media_zlm_ssl",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="node_not_found",
            extra_summary=f"node_id={node_id}",
        )
        raise HTTPException(status_code=404, detail="Media node not found")
    if not bool(node.is_embedded):
        await safe_auth_audit(
            db,
            module="integrations",
            action="put_media_zlm_ssl",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="not_embedded_node",
            extra_summary=f"node_id={node_id}",
        )
        raise HTTPException(
            status_code=400,
            detail="Only embedded media nodes can save ZLM SSL: certificates are loaded by the embedded MediaServer at startup.",  # FIXED: hardcoded Chinese → English
        )
    try:
        merged = validate_and_merge_ssl_pem(
            merged_pem=payload.merged_pem,
            cert_pem=payload.cert_pem,
            key_pem=payload.key_pem,
        )
    except ValueError as e:
        await safe_auth_audit(
            db,
            module="integrations",
            action="put_media_zlm_ssl",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="invalid_pem",
            extra_summary=f"node_id={node_id}; err={str(e)[:120]}",
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    node.zlm_ssl_merged_pem = merged
    await db.commit()
    await safe_auth_audit(
        db,
        module="integrations",
        action="put_media_zlm_ssl",
        source="integrations",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"node_id={node_id}; pem_saved=1",
    )
    return {"status": "ok", "configured": True}


@router.delete("/media-nodes/{node_id}/zlm-ssl")
async def delete_media_node_zlm_ssl(
    node_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    result = await db.execute(select(MediaNode).where(MediaNode.id == node_id))
    node = result.scalars().first()
    if not node:
        await safe_auth_audit(
            db,
            module="integrations",
            action="delete_media_zlm_ssl",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="node_not_found",
            extra_summary=f"node_id={node_id}",
        )
        raise HTTPException(status_code=404, detail="Media node not found")
    if not bool(node.is_embedded):
        await safe_auth_audit(
            db,
            module="integrations",
            action="delete_media_zlm_ssl",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="not_embedded_node",
            extra_summary=f"node_id={node_id}",
        )
        raise HTTPException(status_code=400, detail="Only built-in media nodes support this operation")
    node.zlm_ssl_merged_pem = None
    await db.commit()
    await safe_auth_audit(
        db,
        module="integrations",
        action="delete_media_zlm_ssl",
        source="integrations",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"node_id={node_id}",
    )
    return {"status": "ok", "configured": False}


@router.post("/media-nodes/{node_id}/test")
async def test_media_node(
    node_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"]))
):
    result = await db.execute(select(MediaNode).where(MediaNode.id == node_id))
    node = result.scalars().first()
    if not node:
        await safe_auth_audit(
            db,
            module="integrations",
            action="test_media_node",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="node_not_found",
            extra_summary=f"node_id={node_id}",
        )
        raise HTTPException(status_code=404, detail="Media node not found")
    online, load_value = await _check_media_node(node)
    node.is_online = online
    node.load = load_value
    await db.commit()
    # NAT/容器场景提示：优先 hook_base_url，其次 hook_ip 拼接回调地址
    hook_base = _build_hook_base_url(node)
    await safe_auth_audit(
        db,
        module="integrations",
        action="test_media_node",
        source="integrations",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"node_id={node_id}; online={online}",
    )
    return {"online": online, "load": load_value, "hook_base_url": hook_base}


@router.post("/media-nodes/test-all")
async def test_all_media_nodes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """批量测试所有媒体节点连通性，并刷新在线状态。"""
    result = await db.execute(select(MediaNode))
    nodes = result.scalars().all()
    now = datetime.now(timezone.utc)
    items = []
    for node in nodes:
        online, load_value = await _check_media_node(node)
        node.is_online = online
        node.load = load_value
        if online:
            node.last_seen_at = now
        items.append(
            {
                "id": node.id,
                "ip": node.ip,
                "http_port": node.http_port,
                "online": online,
                "load": load_value,
                "hook_base_url": _build_hook_base_url(node),
            }
        )
    await db.commit()
    await safe_auth_audit(
        db,
        module="integrations",
        action="test_all_media_nodes",
        source="integrations",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"tested_count={len(items)}",
    )
    return {"items": items, "tested_at": now.isoformat()}


@router.get("/media-nodes/{node_id}/zlm-hook-urls")
async def get_media_node_zlm_hook_urls(
    node_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    """返回该媒体节点应配置到 ZLM 的 hook URL 列表（含 secret 参数），用于外置 ZLM/NAT 场景。"""
    result = await db.execute(select(MediaNode).where(MediaNode.id == node_id))
    node = get_or_404(result, detail="MediaNode not found")  # FIXED: ORM查询结果空值判断
    base = _build_hook_base_url(node)
    return {
        "node_id": node.id,
        "hook_base_url": base,
        "hook_urls": _build_zlm_hook_urls(base, node.secret),
    }


@router.get("/media-nodes/{node_id}/zlm-config-snippet")
async def get_media_node_zlm_config_snippet(
    node_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    """返回该媒体节点对应的 ZLM config.ini 关键片段（可直接复制粘贴）。"""
    result = await db.execute(select(MediaNode).where(MediaNode.id == node_id))
    node = get_or_404(result, detail="MediaNode not found")  # FIXED: ORM查询结果空值判断
    base = _build_hook_base_url(node)
    return {
        "node_id": node.id,
        "hook_base_url": base,
        "snippet": _build_zlm_config_snippet(node, base),
    }


@router.post("/media-nodes/{node_id}/activate")
async def activate_media_node(
    node_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"]))
):
    result = await db.execute(select(MediaNode).where(MediaNode.id == node_id))
    node = result.scalars().first()
    if not node:
        await safe_auth_audit(
            db,
            module="integrations",
            action="activate_media_node",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="node_not_found",
            extra_summary=f"node_id={node_id}",
        )
        raise HTTPException(status_code=404, detail="Media node not found")
    active_result = await db.execute(select(SystemSetting).where(SystemSetting.setting_key == "active_media_node_id"))
    setting = active_result.scalars().first()
    if not setting:
        setting = SystemSetting(setting_key="active_media_node_id", setting_value=node.id)
        db.add(setting)
    else:
        setting.setting_value = node.id
    await db.commit()
    await safe_auth_audit(
        db,
        module="integrations",
        action="activate_media_node",
        source="integrations",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"active_media_node_id={node.id}",
    )
    return {"active_media_node_id": node.id}


@router.get("/sources")
async def list_access_sources(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    stmt = select(AccessSource)
    if not current_user.is_superuser:
        stmt = stmt.where(AccessSource.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    records = result.scalars().all()
    return [
        {
            "id": item.id,
            "tenant_id": item.tenant_id,
            "name": item.name,
            "protocol": item.protocol,
            "host": item.host,
            "port": item.port,
            "username": item.username,
            "password": _mask_secret(item.password),
            "path": item.path,
            "stream_name": item.stream_name,
            "enabled": item.enabled,
            "gb_enabled": bool(getattr(item, "gb_enabled", False)),
            "gb_id": getattr(item, "gb_id", None),
            "gb_name": getattr(item, "gb_name", None),
            "gb_parent_gb_id": getattr(item, "gb_parent_gb_id", None),
            "gb_resource_id": getattr(item, "gb_resource_id", None),
            "extra": item.extra or {}
        }
        for item in records
    ]


@router.post("/sources")
async def create_access_source(
    payload: AccessSourcePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"]))
):
    try:
        protocol = _normalize_protocol(payload.protocol)
    except HTTPException as he:
        await safe_auth_audit(
            db,
            module="integrations",
            action="create_access_source",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="unsupported_protocol",
            extra_summary=f"hint={str(he.detail)[:120]}",
        )
        raise he
    source = AccessSource(
        tenant_id=current_user.tenant_id or "default",
        name=payload.name.strip(),
        protocol=protocol,
        host=payload.host.strip(),
        port=payload.port,
        username=(payload.username or "").strip() or None,
        password=(payload.password or "").strip() or None,
        path=(payload.path or "").strip() or None,
        stream_name=(payload.stream_name or "").strip() or None,
        enabled=payload.enabled,
        gb_enabled=bool(payload.gb_enabled),
        gb_id=(payload.gb_id or "").strip() or None,
        gb_name=(payload.gb_name or "").strip() or None,
        gb_parent_gb_id=(payload.gb_parent_gb_id or "").strip() or None,
        gb_resource_id=None,
        extra=payload.extra or {},
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    if bool(payload.gb_enabled):
        gb_id = (payload.gb_id or "").strip()
        gb_name = (payload.gb_name or payload.name or "").strip()
        if not gb_id:
            await safe_auth_audit(
                db,
                module="integrations",
                action="create_access_source",
                source="integrations",
                operator=current_user.username or "unknown",
                result="failed",
                tenant_id=_audit_tid(current_user),
                status_code=400,
                detail="gb_id_required",
                extra_summary=f"source_id={source.id}",
            )
            raise HTTPException(status_code=400, detail="gb_id cannot be empty when GB integration is enabled")
        exists_stmt = select(Resource).where(Resource.gb_id == gb_id)
        if not current_user.is_superuser:
            exists_stmt = exists_stmt.where(Resource.tenant_id == (current_user.tenant_id or "default"))
        if (await db.execute(exists_stmt)).scalars().first():
            await safe_auth_audit(
                db,
                module="integrations",
                action="create_access_source",
                source="integrations",
                operator=current_user.username or "unknown",
                result="failed",
                tenant_id=_audit_tid(current_user),
                status_code=400,
                detail="gb_id_exists",
                extra_summary=f"gb_id={gb_id[:48]}",
            )
            raise HTTPException(status_code=400, detail="gb_id already exists")
        res = Resource(
            tenant_id=current_user.tenant_id or "default",
            asset_id=None,
            gb_id=gb_id,
            name=gb_name,
            node_type="channel",
            parent_gb_id=(payload.gb_parent_gb_id or None),
            status=1,
        )
        db.add(res)
        await db.commit()
        await db.refresh(res)
        source.gb_enabled = True
        source.gb_id = gb_id
        source.gb_name = gb_name
        source.gb_parent_gb_id = (payload.gb_parent_gb_id or "").strip() or None
        source.gb_resource_id = res.id
        await db.commit()
    await safe_auth_audit(
        db,
        module="integrations",
        action="create_access_source",
        source="integrations",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=201,
        detail="ok",
        extra_summary=f"source_id={source.id}; protocol={protocol}; gb_enabled={bool(payload.gb_enabled)}",
    )
    return {"id": source.id}


@router.put("/sources/{source_id}")
async def update_access_source(
    source_id: str,
    payload: AccessSourcePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"]))
):
    stmt = select(AccessSource).where(AccessSource.id == source_id)
    if not current_user.is_superuser:
        stmt = stmt.where(AccessSource.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    source = result.scalars().first()
    if not source:
        await safe_auth_audit(
            db,
            module="integrations",
            action="update_access_source",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="source_not_found",
            extra_summary=f"source_id={source_id}",
        )
        raise HTTPException(status_code=404, detail="Integration source not found")
    try:
        proto = _normalize_protocol(payload.protocol)
    except HTTPException as he:
        await safe_auth_audit(
            db,
            module="integrations",
            action="update_access_source",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="unsupported_protocol",
            extra_summary=f"source_id={source_id}; hint={str(he.detail)[:120]}",
        )
        raise he
    source.name = payload.name.strip()
    source.protocol = proto
    source.host = payload.host.strip()
    source.port = payload.port
    source.username = (payload.username or "").strip() or None
    password = (payload.password or "").strip()
    if password:
        source.password = password
    source.path = (payload.path or "").strip() or None
    source.stream_name = (payload.stream_name or "").strip() or None
    source.enabled = payload.enabled
    source.extra = payload.extra or {}
    gb_enabled = bool(payload.gb_enabled)
    gb_id = (payload.gb_id or "").strip()
    gb_name = (payload.gb_name or payload.name or "").strip()
    gb_parent = (payload.gb_parent_gb_id or "").strip() or None

    if not gb_enabled:
        if getattr(source, "gb_resource_id", None):
            old_id = str(source.gb_resource_id)
            try:
                old_res = (await db.execute(select(Resource).where(Resource.id == old_id))).scalars().first()
                if old_res:
                    await db.delete(old_res)
            except Exception as e:
                logger.debug(f"非关键操作失败: {e}")
        source.gb_enabled = False
        source.gb_id = None
        source.gb_name = None
        source.gb_parent_gb_id = None
        source.gb_resource_id = None
    else:
        if not gb_id:
            raise HTTPException(status_code=400, detail="gb_id cannot be empty when GB integration is enabled")
        if getattr(source, "gb_resource_id", None):
            res = (await db.execute(select(Resource).where(Resource.id == str(source.gb_resource_id)))).scalars().first()
            if res:
                if res.gb_id != gb_id:
                    exists_stmt = select(Resource).where(Resource.gb_id == gb_id, Resource.id != res.id)
                    if not current_user.is_superuser:
                        exists_stmt = exists_stmt.where(Resource.tenant_id == (current_user.tenant_id or "default"))
                    if (await db.execute(exists_stmt)).scalars().first():
                        raise HTTPException(status_code=400, detail="gb_id already exists")
                res.gb_id = gb_id
                res.name = gb_name
                res.parent_gb_id = gb_parent
        else:
            exists_stmt = select(Resource).where(Resource.gb_id == gb_id)
            if not current_user.is_superuser:
                exists_stmt = exists_stmt.where(Resource.tenant_id == (current_user.tenant_id or "default"))
            if (await db.execute(exists_stmt)).scalars().first():
                raise HTTPException(status_code=400, detail="gb_id already exists")
            res = Resource(
                tenant_id=current_user.tenant_id or "default",
                asset_id=None,
                gb_id=gb_id,
                name=gb_name,
                node_type="channel",
                parent_gb_id=gb_parent,
                status=1,
            )
            db.add(res)
            await db.flush()
            source.gb_resource_id = res.id
        source.gb_enabled = True
        source.gb_id = gb_id
        source.gb_name = gb_name
        source.gb_parent_gb_id = gb_parent
    await db.commit()
    try:
        if (source.protocol or "").upper() == "RTMP":
            pc = (await db.execute(select(PushChannel).where(PushChannel.id == source_id))).scalars().first()
            if pc:
                pc.stream_name = normalize_stream_name(source.stream_name or source.name or source.id, fallback=source.id)
                await db.commit()
    except Exception as e:
        logger.debug(f"非关键操作失败: {e}")
    await safe_auth_audit(
        db,
        module="integrations",
        action="update_access_source",
        source="integrations",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"source_id={source_id}; protocol={proto}; gb_enabled={gb_enabled}",
    )
    return {"status": "ok"}


@router.delete("/sources/{source_id}")
async def delete_access_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"]))
):
    stmt = select(AccessSource).where(AccessSource.id == source_id)
    if not current_user.is_superuser:
        stmt = stmt.where(AccessSource.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    source = result.scalars().first()
    if not source:
        await safe_auth_audit(
            db,
            module="integrations",
            action="delete_access_source",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="source_not_found",
            extra_summary=f"source_id={source_id}",
        )
        raise HTTPException(status_code=404, detail="Integration source not found")
    try:
        pc = (await db.execute(select(PushChannel).where(PushChannel.id == source_id))).scalars().first()
        if pc:
            await db.delete(pc)
    except Exception as e:
        logger.debug(f"非关键操作失败: {e}")
    await db.delete(source)
    await db.commit()
    await safe_auth_audit(
        db,
        module="integrations",
        action="delete_access_source",
        source="integrations",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"source_id={source_id}",
    )
    return {"status": "ok"}


@router.get("/sources/{source_id}/push-url")
async def get_rtmp_push_url(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """RTMP 推流地址：接入源协议为 RTMP 时，返回推流 URL，供编码器/推流端使用。"""
    stmt = select(AccessSource).where(AccessSource.id == source_id, AccessSource.enabled == True)
    if not current_user.is_superuser:
        stmt = stmt.where(AccessSource.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    source = get_or_404(result, detail="AccessSource not found")  # FIXED: ORM查询结果空值判断
    if source.protocol.upper() != "RTMP":
        raise HTTPException(status_code=400, detail="Only RTMP integration source supports getting push URL")
    stream_name = normalize_stream_name(source.stream_name or source.name or source.id, fallback=source.id)
    rtmp_host = getattr(settings, "STREAM_PUBLIC_HOST", settings.MEDIA_SERVER_HOST)
    rtmp_port = getattr(settings, "MEDIA_SERVER_RTMP_PORT", 1935)
    selection_reason = "global"
    try:
        active_id = await get_active_media_node_id(db)
        db_node = await get_db_media_node_by_id(db, active_id) if active_id else None
        if not db_node:
            db_node = await select_best_db_node(db)
        if db_node:
            rtmp_host = db_node.public_host or rtmp_host
            rtmp_port = db_node.rtmp_port or rtmp_port
            selection_reason = "active" if (active_id and db_node.id == active_id) else "auto"
    except Exception as e:
        logger.debug(f"非关键操作失败: {e}")
    push_url = f"rtmp://{rtmp_host}:{rtmp_port}/live/{stream_name}"
    push_key_enabled = False
    push_key_hint = ""
    try:
        pc = (await db.execute(select(PushChannel).where(PushChannel.id == source_id))).scalars().first()
        if pc and pc.push_key_enabled and pc.push_key_prefix and pc.hashed_push_key:
            push_key_enabled = True
            push_key_hint = f"push_{pc.push_key_prefix}.***"
    except Exception as e:
        logger.debug(f"非关键操作失败: {e}")
    try:
        operator = getattr(current_user, "username", None) or getattr(current_user, "email", None) or str(getattr(current_user, "id", "unknown"))
        await audit_center_service.log(
            db=db,
            module="media_nodes",
            action="select_node_for_rtmp_push_url",
            operator=str(operator),
            result="success",
            summary=f"reason={selection_reason}; source_id={source_id}; stream={stream_name}; host={rtmp_host}; port={rtmp_port}",
        )
    except Exception as e:
        logger.debug(f"非关键操作失败: {e}")
    push_url_with_key_hint = push_url
    if push_key_enabled and push_key_hint:
        push_url_with_key_hint = f"{push_url}?pushKey={push_key_hint}"
    return {
        "push_url": push_url,
        "push_url_with_key_hint": push_url_with_key_hint,
        "push_key_enabled": push_key_enabled,
        "push_key_hint": push_key_hint,
        "stream_name": stream_name,
        "app": "live",
    }


@router.post("/sources/{source_id}/actions/desired-state")
async def set_access_source_desired_state(
    source_id: str,
    payload: DesiredStatePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    stmt = select(AccessSource).where(AccessSource.id == source_id)
    if not current_user.is_superuser:
        stmt = stmt.where(AccessSource.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    source = result.scalars().first()
    if not source:
        await safe_auth_audit(
            db,
            module="integrations",
            action="set_access_source_desired_state",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="source_not_found",
            extra_summary=f"source_id={source_id}",
        )
        raise HTTPException(status_code=404, detail="Integration source not found")
    protocol = (source.protocol or "").upper()
    if protocol not in {"RTMP", "RTSP", "ONVIF", "SDK"}:
        await safe_auth_audit(
            db,
            module="integrations",
            action="set_access_source_desired_state",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="protocol_not_supported",
            extra_summary=f"source_id={source_id}; protocol={protocol}",
        )
        raise HTTPException(status_code=400, detail="This integration source does not support desired state")
    state = (payload.state or "").strip().lower()
    if state not in {"running", "stopped"}:
        await safe_auth_audit(
            db,
            module="integrations",
            action="set_access_source_desired_state",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="invalid_state",
            extra_summary=f"source_id={source_id}; state={(payload.state or '')[:24]}",
        )
        raise HTTPException(status_code=400, detail="state only supports running/stopped")
    now_iso = datetime.now(timezone.utc).isoformat()
    await _update_source_runtime(db, source, {
        "desired.state": state,
        "desired.updated_at": now_iso,
        "desired.updated_by": getattr(current_user, "username", None) or getattr(current_user, "email", None) or str(getattr(current_user, "id", "")),
    })
    stream_name = normalize_stream_name(source.stream_name or source.name or source.id, fallback=source.id)
    if payload.enforce and state == "stopped":
        try:
            await close_zlm_stream(app="live", stream=stream_name, node_id=None)
            try:
                ffmpeg_proxy_manager.stop(source.id)
            except Exception as e:
                logger.debug(f"非关键操作失败: {e}")
            prefix = "runtime.rtmp" if protocol == "RTMP" else "runtime.proxy"
            await _update_source_runtime(db, source, {
                f"{prefix}.last_enforce_stop_at": now_iso,
                f"{prefix}.last_enforce_stop_ok": True,
                f"{prefix}.last_enforce_stop_message": "",
            })
        except Exception as e:
            prefix = "runtime.rtmp" if protocol == "RTMP" else "runtime.proxy"
            await _update_source_runtime(db, source, {
                f"{prefix}.last_enforce_stop_at": now_iso,
                f"{prefix}.last_enforce_stop_ok": False,
                f"{prefix}.last_enforce_stop_message": str(e)[:200],
            })
    if payload.enforce and state == "running":
        if protocol == "RTMP":
            await _update_source_runtime(db, source, {
                "runtime.rtmp.last_enforce_start_at": now_iso,
                "runtime.rtmp.last_enforce_start_ok": False,
                "runtime.rtmp.last_enforce_start_message": "RTMP 推流需外部推流端发起，平台无法主动拉起",
            })
        else:
            target_url = ""
            if protocol == "RTSP":
                auth = ""
                if source.username:
                    auth = source.username
                    if source.password:
                        auth = f"{auth}:{source.password}"
                    auth = f"{auth}@"
                path = (source.path or "").lstrip("/")
                target_url = f"rtsp://{auth}{source.host}:{source.port}/{path}"
            elif protocol == "ONVIF":
                direct = (source.extra or {}).get("rtsp_url")
                if direct:
                    target_url = str(direct)
                else:
                    auth = ""
                    if source.username:
                        auth = source.username
                        if source.password:
                            auth = f"{auth}:{source.password}"
                        auth = f"{auth}@"
                    path = (source.path or "Streaming/Channels/101").lstrip("/")
                    target_url = f"rtsp://{auth}{source.host}:{source.port or 554}/{path}"
            elif protocol == "SDK":
                direct = (source.extra or {}).get("play_url")
                if not direct:
                    await _update_source_runtime(db, source, {
                        "runtime.proxy.last_enforce_start_at": now_iso,
                        "runtime.proxy.last_enforce_start_ok": False,
                        "runtime.proxy.last_enforce_start_message": "SDK integration source requires extra.play_url",
                    })
                    raise HTTPException(status_code=400, detail="SDK integration source requires extra.play_url")
                target_url = str(direct)

            ffmpeg_cmd_key = (source.extra or {}).get("ffmpeg_cmd_key") or (source.extra or {}).get("ffmpeg_cmd_id")
            if ffmpeg_cmd_key:
                cmd_stmt = select(FfmpegCmd).where(FfmpegCmd.id == str(ffmpeg_cmd_key))
                if not current_user.is_superuser:
                    cmd_stmt = cmd_stmt.where(FfmpegCmd.tenant_id == (current_user.tenant_id or "default"))
                cmd_row = (await db.execute(cmd_stmt)).scalars().first()
                if not cmd_row:
                    raise HTTPException(status_code=400, detail="ffmpeg_cmd_key invalid")
                if str(getattr(cmd_row, "enabled", "true") or "true").lower() not in {"true", "1", "yes"}:
                    raise HTTPException(status_code=400, detail="ffmpeg_cmd is disabled")

                proxy_host = settings.MEDIA_SERVER_HOST
                proxy_rtmp_port = settings.MEDIA_SERVER_RTMP_PORT
                selection_reason = "global"
                try:
                    active_id = await get_active_media_node_id(db)
                    db_node = await get_db_media_node_by_id(db, active_id) if active_id else None
                    if not db_node:
                        db_node = await select_best_db_node(db)
                    if db_node:
                        proxy_host = db_node.host or proxy_host
                        proxy_rtmp_port = int(getattr(db_node, "rtmp_port", 0) or 0) or proxy_rtmp_port
                        selection_reason = "active" if (active_id and db_node.id == active_id) else "auto"
                except Exception as e:
                    logger.debug(f"非关键操作失败: {e}")

                output_url = f"rtmp://{proxy_host}:{proxy_rtmp_port}/live/{stream_name}"
                cmd_tpl = str(cmd_row.cmd_template or "")
                cmd = (
                    cmd_tpl.replace("{input}", target_url)
                    .replace("{output}", output_url)
                    .replace("{stream}", stream_name)
                    .replace("{app}", "live")
                )
                try:
                    ffmpeg_proxy_manager.start(source.id, cmd)
                    await _update_source_runtime(db, source, {
                        "runtime.proxy.last_enforce_start_at": now_iso,
                        "runtime.proxy.last_enforce_start_ok": True,
                        "runtime.proxy.last_enforce_start_message": "",
                        "runtime.proxy.last_start_node": f"{proxy_host}:{proxy_rtmp_port}",
                        "runtime.proxy.last_start_reason": f"manual_enforce ffmpeg reason={selection_reason}",
                        "runtime.proxy.last_target_url": str(target_url)[:200],
                        "runtime.proxy.mode": "ffmpeg",
                        "runtime.proxy.ffmpeg_cmd_key": str(cmd_row.id),
                    })
                except Exception as e:
                    await _update_source_runtime(db, source, {
                        "runtime.proxy.last_enforce_start_at": now_iso,
                        "runtime.proxy.last_enforce_start_ok": False,
                        "runtime.proxy.last_enforce_start_message": str(e)[:200],
                        "runtime.proxy.mode": "ffmpeg",
                        "runtime.proxy.ffmpeg_cmd_key": str(cmd_row.id),
                    })
                    raise HTTPException(status_code=502, detail=f"FFmpeg start failed: {str(e)}")
                await safe_auth_audit(
                    db,
                    module="integrations",
                    action="set_access_source_desired_state",
                    source="integrations",
                    operator=current_user.username or "unknown",
                    result="success",
                    tenant_id=_audit_tid(current_user),
                    status_code=200,
                    detail="ok",
                    extra_summary=f"source_id={source_id}; state={state}; enforce={bool(payload.enforce)}; path=ffmpeg",
                )
                return {"ok": True, "desired_state": state}

            proxy_host = settings.MEDIA_SERVER_HOST
            proxy_http_port = settings.MEDIA_SERVER_HTTP_PORT
            proxy_secret = settings.MEDIA_SERVER_SECRET
            selection_reason = "global"
            try:
                active_id = await get_active_media_node_id(db)
                db_node = await get_db_media_node_by_id(db, active_id) if active_id else None
                if not db_node:
                    db_node = await select_best_db_node(db)
                if db_node:
                    proxy_host = db_node.host or proxy_host
                    proxy_http_port = db_node.http_port or proxy_http_port
                    proxy_secret = db_node.secret or proxy_secret
                    selection_reason = "active" if (active_id and db_node.id == active_id) else "auto"
            except Exception as e:
                logger.debug(f"非关键操作失败: {e}")

            proxy_url = f"http://{proxy_host}:{proxy_http_port}/index/api/addStreamProxy"
            try:
                client = await _get_zlm_client()
                response = await client.get(
                        proxy_url,
                        params={
                            "secret": proxy_secret,
                            "vhost": "__defaultVhost__",
                            "app": "live",
                            "stream": stream_name,
                            "url": target_url,
                            "enable_hls": 1,
                            "enable_mp4": 0,
                            "rtp_type": 0,
                        },
                    )
                if response.status_code >= 400:
                    raise HTTPException(status_code=502, detail=f"Proxy request failed: {response.status_code}")  # FIXED: hardcoded Chinese → English
                body = response.json()
                if body.get("code") not in {0, "0"}:
                    raise HTTPException(status_code=502, detail=f"Proxy request failed: {body.get('msg') or body}")  # FIXED: hardcoded Chinese → English
                safe_target = target_url
                if "://" in safe_target and "@" in safe_target.split("://", 1)[1]:
                    prefix, rest = safe_target.split("://", 1)
                    head = rest.split("@", 1)[0]
                    if ":" in head:
                        user = head.split(":", 1)[0]
                        safe_target = f"{prefix}://{user}:***@{rest.split('@', 1)[1]}"
                await _update_source_runtime(db, source, {
                    "runtime.proxy.last_enforce_start_at": now_iso,
                    "runtime.proxy.last_enforce_start_ok": True,
                    "runtime.proxy.last_enforce_start_message": "",
                    "runtime.proxy.last_start_node": f"{proxy_host}:{proxy_http_port}",
                    "runtime.proxy.last_start_reason": f"manual_enforce reason={selection_reason}",
                    "runtime.proxy.last_target_url": safe_target[:200],
                })
            except HTTPException as he:
                await _update_source_runtime(db, source, {
                    "runtime.proxy.last_enforce_start_at": now_iso,
                    "runtime.proxy.last_enforce_start_ok": False,
                    "runtime.proxy.last_enforce_start_message": str(he.detail)[:200],
                    "runtime.proxy.last_start_node": f"{proxy_host}:{proxy_http_port}",
                })
                raise
            except Exception as e:
                await _update_source_runtime(db, source, {
                    "runtime.proxy.last_enforce_start_at": now_iso,
                    "runtime.proxy.last_enforce_start_ok": False,
                    "runtime.proxy.last_enforce_start_message": str(e)[:200],
                    "runtime.proxy.last_start_node": f"{proxy_host}:{proxy_http_port}",
                })
                raise HTTPException(status_code=502, detail=f"Proxy request error: {str(e)}")  # FIXED: hardcoded Chinese → English
    await safe_auth_audit(
        db,
        module="integrations",
        action="set_access_source_desired_state",
        source="integrations",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"source_id={source_id}; state={state}; enforce={bool(payload.enforce)}; path=default",
    )
    return {"ok": True, "desired_state": state}


@router.post("/sources/{source_id}/actions/set-enabled")
async def set_access_source_enabled(
    source_id: str,
    payload: SourceEnabledPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    stmt = select(AccessSource).where(AccessSource.id == source_id)
    if not current_user.is_superuser:
        stmt = stmt.where(AccessSource.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    source = result.scalars().first()
    if not source:
        await safe_auth_audit(
            db,
            module="integrations",
            action="set_access_source_enabled",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="source_not_found",
            extra_summary=f"source_id={source_id}",
        )
        raise HTTPException(status_code=404, detail="Integration source not found")
    source.enabled = bool(payload.enabled)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        await safe_auth_audit(
            db,
            module="integrations",
            action="set_access_source_enabled",
            source="integrations",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=500,
            detail="save_error",
            extra_summary=f"source_id={source_id}",
        )
        raise HTTPException(status_code=500, detail="Save failed")  # FIXED: hardcoded Chinese → English
    await safe_auth_audit(
        db,
        module="integrations",
        action="set_access_source_enabled",
        source="integrations",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"source_id={source_id}; enabled={source.enabled}",
    )
    return {"ok": True, "enabled": source.enabled}


@router.post("/sources/{source_id}/test")
async def test_access_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"]))
):
    stmt = select(AccessSource).where(AccessSource.id == source_id)
    if not current_user.is_superuser:
        stmt = stmt.where(AccessSource.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    source = get_or_404(result, detail="AccessSource not found")  # FIXED: ORM查询结果空值判断
    protocol = source.protocol.upper()
    now_iso = datetime.now(timezone.utc).isoformat()
    if protocol in {"ONVIF", "RTSP"}:
        await _update_source_runtime(db, source, {
            "runtime.last_test_at": now_iso,
            "runtime.last_test_ok": True,
            "runtime.last_test_message": "Parameters saved, you can test playback directly",  # FIXED: hardcoded Chinese → English
        })
        return {"ok": True, "message": "Parameters saved, you can test playback directly"}  # FIXED: hardcoded Chinese → English
    if protocol == "SDK":
        await _update_source_runtime(db, source, {
            "runtime.last_test_at": now_iso,
            "runtime.last_test_ok": True,
            "runtime.last_test_message": "SDK source saved, please verify plugin or SDK gateway is available",  # FIXED: hardcoded Chinese → English
        })
        return {"ok": True, "message": "SDK source saved, please verify plugin or SDK gateway is available"}  # FIXED: hardcoded Chinese → English
    await _update_source_runtime(db, source, {
        "runtime.last_test_at": now_iso,
        "runtime.last_test_ok": True,
        "runtime.last_test_message": "GB28181 is verified through device registration flow",  # FIXED: hardcoded Chinese → English
    })
    return {"ok": True, "message": "GB28181 is verified through device registration flow"}  # FIXED: hardcoded Chinese → English


@router.post("/sources/{source_id}/play")
async def play_access_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    stmt = select(AccessSource).where(AccessSource.id == source_id, AccessSource.enabled == True)
    if not current_user.is_superuser:
        stmt = stmt.where(AccessSource.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    source = get_or_404(result, detail="AccessSource not found")  # FIXED: ORM查询结果空值判断
    now_iso = datetime.now(timezone.utc).isoformat()
    stream_name = normalize_stream_name(source.stream_name or source.name or source.id, fallback=source.id)
    target_url = ""
    protocol = source.protocol.upper()
    if protocol == "RTSP":
        auth = ""
        if source.username:
            auth = source.username
            if source.password:
                auth = f"{auth}:{source.password}"
            auth = f"{auth}@"
        path = (source.path or "").lstrip("/")
        target_url = f"rtsp://{auth}{source.host}:{source.port}/{path}"
    elif protocol == "ONVIF":
        direct = (source.extra or {}).get("rtsp_url")
        if direct:
            target_url = str(direct)
        else:
            auth = ""
            if source.username:
                auth = source.username
                if source.password:
                    auth = f"{auth}:{source.password}"
                auth = f"{auth}@"
            path = (source.path or "Streaming/Channels/101").lstrip("/")
            target_url = f"rtsp://{auth}{source.host}:{source.port or 554}/{path}"
    elif protocol == "SDK":
        direct = (source.extra or {}).get("play_url")
        if not direct:
            await _update_source_runtime(db, source, {
                "runtime.last_play_at": now_iso,
                "runtime.last_play_ok": False,
                "runtime.last_play_error": "SDK integration source requires extra.play_url",
            })
            raise HTTPException(status_code=400, detail="SDK integration source requires extra.play_url")
        target_url = str(direct)
    elif protocol == "RTMP":
        # RTMP 推流接入：无需拉流，播放端直接拉 live/{stream_name}；推流地址见 GET push-url
        media_host = getattr(settings, "STREAM_PUBLIC_HOST", settings.MEDIA_SERVER_HOST)
        media_port = getattr(settings, "STREAM_PUBLIC_HTTP_PORT", settings.MEDIA_SERVER_HTTP_PORT)
        selection_reason = "global"
        try:
            active_id = await get_active_media_node_id(db)
            db_node = await get_db_media_node_by_id(db, active_id) if active_id else None
            if not db_node:
                db_node = await select_best_db_node(db)
            if db_node:
                media_host = db_node.public_host or media_host
                media_port = db_node.public_http_port or media_port
                selection_reason = "active" if (active_id and db_node.id == active_id) else "auto"
        except Exception as e:
            logger.debug(f"非关键操作失败: {e}")
        try:
            operator = getattr(current_user, "username", None) or getattr(current_user, "email", None) or str(getattr(current_user, "id", "unknown"))
            await audit_center_service.log(
                db=db,
                module="media_nodes",
                action="select_node_for_rtmp_playback_urls",
                operator=str(operator),
                result="success",
                summary=f"reason={selection_reason}; source_id={source_id}; stream={stream_name}; host={media_host}; http_port={media_port}",
            )
        except Exception as e:
            logger.debug(f"非关键操作失败: {e}")
        return {
            "app": "live",
            "stream": stream_name,
            "codec": str((source.extra or {}).get("codec") or "h264").lower(),
            "flv": f"http://{media_host}:{media_port}/live/{stream_name}.live.flv",
            "hls": f"http://{media_host}:{media_port}/live/{stream_name}/hls.m3u8",
            "webrtc": f"http://{media_host}:{media_port}/index/api/webrtc?app=live&stream={stream_name}&type=play",
        }
    else:
        await _update_source_runtime(db, source, {
            "runtime.last_play_at": now_iso,
            "runtime.last_play_ok": False,
            "runtime.last_play_error": "GB28181 access requires device/channel playback API",  # FIXED: hardcoded Chinese → English
        })
        raise HTTPException(status_code=400, detail="For GB28181 access, please use the device/channel playback API")  # FIXED: hardcoded Chinese → English

    # 代理拉流：优先使用运维中心配置的活动媒体节点，否则自动选一个节点；最后回退全局配置
    proxy_host = settings.MEDIA_SERVER_HOST
    proxy_http_port = settings.MEDIA_SERVER_HTTP_PORT
    proxy_secret = settings.MEDIA_SERVER_SECRET
    public_host = settings.STREAM_PUBLIC_HOST
    public_http_port = settings.STREAM_PUBLIC_HTTP_PORT
    selection_reason = "global"
    try:
        active_id = await get_active_media_node_id(db)
        db_node = await get_db_media_node_by_id(db, active_id) if active_id else None
        if not db_node:
            db_node = await select_best_db_node(db)
        if db_node:
            proxy_host = db_node.host or proxy_host
            proxy_http_port = db_node.http_port or proxy_http_port
            proxy_secret = db_node.secret or proxy_secret
            public_host = db_node.public_host or public_host
            public_http_port = db_node.public_http_port or public_http_port
            selection_reason = "active" if (active_id and db_node.id == active_id) else "auto"
    except Exception as e:
        logger.debug(f"非关键操作失败: {e}")
    try:
        operator = getattr(current_user, "username", None) or getattr(current_user, "email", None) or str(getattr(current_user, "id", "unknown"))
        await audit_center_service.log(
            db=db,
            module="media_nodes",
            action="select_node_for_add_stream_proxy",
            operator=str(operator),
            result="success",
            summary=f"reason={selection_reason}; source_id={source_id}; stream={stream_name}; proxy={proxy_host}:{proxy_http_port}; public={public_host}:{public_http_port}",
        )
    except Exception as e:
        logger.debug(f"非关键操作失败: {e}")

    proxy_url = f"http://{proxy_host}:{proxy_http_port}/index/api/addStreamProxy"
    try:
        client = await _get_zlm_client()
        response = await client.get(
                proxy_url,
                params={
                    "secret": proxy_secret,
                    "vhost": "__defaultVhost__",
                    "app": "live",
                    "stream": stream_name,
                    "url": target_url,
                    "enable_hls": 1,
                    "enable_mp4": 0,
                    "rtp_type": 0
                },
            )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Proxy request failed: {response.status_code}")  # FIXED: hardcoded Chinese → English
        body = response.json()
        if body.get("code") not in {0, "0"}:
            raise HTTPException(status_code=502, detail=f"Proxy request failed: {body.get('msg') or body}")  # FIXED: hardcoded Chinese → English
    except HTTPException as he:
        await _update_source_runtime(db, source, {
            "runtime.last_play_at": now_iso,
            "runtime.last_play_ok": False,
            "runtime.last_play_error": str(he.detail),
            "runtime.last_play_stream": stream_name,
            "runtime.last_play_target_url": target_url,
            "runtime.last_play_node": f"{proxy_host}:{proxy_http_port}",
        })
        raise
    except Exception as e:
        await _update_source_runtime(db, source, {
            "runtime.last_play_at": now_iso,
            "runtime.last_play_ok": False,
            "runtime.last_play_error": f"Proxy request error: {str(e)}",  # FIXED: hardcoded Chinese → English
            "runtime.last_play_stream": stream_name,
            "runtime.last_play_target_url": target_url,
            "runtime.last_play_node": f"{proxy_host}:{proxy_http_port}",
        })
        raise HTTPException(status_code=502, detail=f"Proxy request error: {str(e)}")  # FIXED: hardcoded Chinese → English
    media_host = public_host
    media_port = public_http_port
    payload = {
        "app": "live",
        "stream": stream_name,
        "codec": str((source.extra or {}).get("codec") or "h264").lower(),
        "flv": f"http://{media_host}:{media_port}/live/{stream_name}.live.flv",
        "hls": f"http://{media_host}:{media_port}/live/{stream_name}/hls.m3u8",
        "webrtc": f"http://{media_host}:{media_port}/index/api/webrtc?app=live&stream={stream_name}&type=play"
    }
    await _update_source_runtime(db, source, {
        "runtime.last_play_at": now_iso,
        "runtime.last_play_ok": True,
        "runtime.last_play_error": "",
        "runtime.last_play_stream": stream_name,
        "runtime.last_play_target_url": target_url,
        "runtime.last_play_node": f"{proxy_host}:{proxy_http_port}",
        "runtime.last_play_urls": {"flv": payload["flv"], "hls": payload["hls"], "webrtc": payload["webrtc"]},
    })
    return payload
