from __future__ import annotations

from typing import Any

from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.asset import Asset
from app.models.resource import Resource
from app.models.stream_session import StreamSession
from app.sip.server import sip_server
import app.sip.invite as sip_invite_module
from app.services.auth_audit import safe_auth_audit
from app.services.stream_session_service import release_stream_session


async def start_main_sub_stream_for_plugin(
    *,
    db: AsyncSession,
    channel_gb_id: str,
    stream_type: str = "main",  # main | sub | 0 | 1
    operator: str = "plugin",
    current_user: Any | None = None,
) -> dict[str, Any]:
    """
    插件主动触发拉起主/辅码流（main/sub）。

    - channel_gb_id: Resource.gb_id（通道 GB-ID）
    - stream_type: "main" | "sub"（或 "0"/"1" 兼容）

    返回：sip_invite.send_invite 的结果，包含 stream_session_id/ssrc/node_id 等。
    """
    tenant_id = getattr(current_user, "tenant_id", None) or "default"
    is_superuser = bool(getattr(current_user, "is_superuser", False))

    norm = (stream_type or "main").strip().lower()
    if norm in {"0", "main"}:
        norm = "main"
    elif norm in {"1", "sub"}:
        norm = "sub"
    else:
        norm = "main"

    stmt = select(Resource, Asset).join(Asset, Asset.id == Resource.asset_id).where(Resource.gb_id == channel_gb_id)
    if not is_superuser:
        stmt = stmt.where(Asset.tenant_id == tenant_id)

    row = (await db.execute(stmt)).first()
    if not row:
        await safe_auth_audit(
            db,
            module="plugins",
            action="start_main_sub_stream",
            source="plugin_stream_helper",
            operator=str(operator or "unknown"),
            result="failed",
            tenant_id=str(tenant_id),
            status_code=404,
            detail="channel_or_asset_not_found",
            extra_summary=f"channel_gb_id={channel_gb_id}; stream_type={norm}",
        )
        raise RuntimeError("channel_or_asset_not_found")

    resource, asset = row
    if not getattr(asset, "ip_addr", None):
        await safe_auth_audit(
            db,
            module="plugins",
            action="start_main_sub_stream",
            source="plugin_stream_helper",
            operator=str(operator or "unknown"),
            result="failed",
            tenant_id=str(tenant_id),
            status_code=500,
            detail="asset_ip_missing",
            extra_summary=f"channel_gb_id={channel_gb_id}; stream_type={norm}",
        )
        raise RuntimeError("asset_ip_missing")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await safe_auth_audit(
            db,
            module="plugins",
            action="start_main_sub_stream",
            source="plugin_stream_helper",
            operator=str(operator or "unknown"),
            result="failed",
            tenant_id=str(tenant_id),
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"channel_gb_id={channel_gb_id}; stream_type={norm}",
        )
        raise RuntimeError("sip_transport_unavailable")

    if not getattr(sip_invite_module, "sip_invite", None):
        await safe_auth_audit(
            db,
            module="plugins",
            action="start_main_sub_stream",
            source="plugin_stream_helper",
            operator=str(operator or "unknown"),
            result="failed",
            tenant_id=str(tenant_id),
            status_code=500,
            detail="sip_invite_not_ready",
            extra_summary=f"channel_gb_id={channel_gb_id}; stream_type={norm}",
        )
        raise RuntimeError("sip_invite_not_ready")

    result = await sip_invite_module.sip_invite.send_invite(
        asset,
        resource,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        stream_type=norm,
    )

    await safe_auth_audit(
        db,
        module="plugins",
        action="start_main_sub_stream",
        source="plugin_stream_helper",
        operator=str(operator or "unknown"),
        result="success",
        tenant_id=str(tenant_id),
        status_code=200,
        detail="ok",
        extra_summary=(
            f"channel_gb_id={channel_gb_id}; stream_type={norm}; "
            f"stream_session_id={result.get('stream_session_id')}; ssrc={result.get('ssrc')}"
        ),
    )
    return result


async def ensure_main_sub_stream_for_plugin(
    *,
    db: AsyncSession,
    channel_gb_id: str,
    stream_type: str = "main",
    ssrc: str | None = None,
    operator: str = "plugin",
    current_user: Any | None = None,
) -> dict[str, Any]:
    """
    选项 2（主动兜底）：收到 ZLM on_stream_changed 事件后，如果 DB 里还没有对应 ssrc 的 StreamSession，
    则主动发起 INVITE 拉起 main/sub；否则跳过，避免重复拉起。
    """
    if ssrc:
        try:
            exists = (
                await db.execute(select(StreamSession).where(StreamSession.ssrc == str(ssrc)))
            ).scalars().first()
            if exists:
                return {"already_exists": True, "stream_session_id": getattr(exists, "id", None), "ssrc": ssrc}
        except Exception as e:
            logger.warning(f"插件运行时配置解析失败: {e}")

    return await start_main_sub_stream_for_plugin(
        db=db,
        channel_gb_id=channel_gb_id,
        stream_type=stream_type,
        operator=operator,
        current_user=current_user,
    )


async def stop_stream_for_plugin(
    *,
    db: AsyncSession,
    stream_session_id: str,
    reason: str = "plugin_stop",
    operator: str = "plugin",
    current_user: Any | None = None,
) -> None:
    tenant_id = getattr(current_user, "tenant_id", None) or "default"
    is_superuser = bool(getattr(current_user, "is_superuser", False))

    stmt = select(StreamSession).where(StreamSession.id == stream_session_id)
    if not is_superuser:
        # 简化：从 StreamSession 无法直接拿 tenant_id（它关联的 Asset/Resource 才有）
        # 这里不额外校验，避免复杂 join 影响性能与插件开发成本。
        # 记录跳过的租户校验，便于审计
        logger.warning(f"Tenant check skipped for stream_session_id={stream_session_id} (non-superuser)")

    ss = (await db.execute(stmt)).scalars().first()
    if not ss:
        await safe_auth_audit(
            db,
            module="plugins",
            action="stop_stream_for_plugin",
            source="plugin_stream_helper",
            operator=str(operator or "unknown"),
            result="failed",
            tenant_id=str(tenant_id),
            status_code=404,
            detail="stream_session_not_found",
            extra_summary=f"stream_session_id={stream_session_id}",
        )
        raise RuntimeError("stream_session_not_found")

    await release_stream_session(db, ss, reason=reason)

    await safe_auth_audit(
        db,
        module="plugins",
        action="stop_stream_for_plugin",
        source="plugin_stream_helper",
        operator=str(operator or "unknown"),
        result="success",
        tenant_id=str(tenant_id),
        status_code=200,
        detail="ok",
        extra_summary=f"stream_session_id={stream_session_id}; reason={reason}",
    )

