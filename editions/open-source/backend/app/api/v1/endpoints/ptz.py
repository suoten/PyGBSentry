from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.models.resource import Resource
from app.models.asset import Asset
from app.sip.commander import sip_commander
from app.sip.server import sip_server
from app.services.auth_audit import safe_auth_audit

router = APIRouter()


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"

@router.post("/{channel_id}/control")
async def control_ptz(
    channel_id: str,
    left_right: int = Query(0, description="0:停止 1:左移 2:右移"),
    up_down: int = Query(0, description="0:停止 1:上移 2:下移"),
    in_out: int = Query(0, description="0:停止 1:缩小 2:放大"),
    move_speed: int = Query(127, ge=0, le=255, description="移动速度 (0-255)"),
    zoom_speed: int = Query(16, ge=0, le=255, description="缩放速度 (0-255)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    stmt = select(Resource, Asset).join(Asset, Asset.id == Resource.asset_id).where(Resource.gb_id == channel_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))

    result = await db.execute(stmt)
    row = result.first()
    if not row:
        await safe_auth_audit(
            db,
            module="control",
            action="ptz_control",
            source="device_control",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="channel_not_found",
            extra_summary=f"channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Channel not found or no permission")

    resource, asset = row

    if not sip_commander:
        await safe_auth_audit(
            db,
            module="control",
            action="ptz_control",
            source="device_control",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=500,
            detail="sip_commander_unavailable",
            extra_summary=f"channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="SIP service not ready")

    transport_info = (
        (asset.ip_addr, asset.port),
        asset.transport or "UDP",
        sip_server.udp_transport if (asset.transport or "UDP") == "UDP" else sip_server.tcp_server
    )

    await sip_commander.send_ptz_cmd(
        device_id=asset.gb_id,
        channel_id=resource.gb_id,
        transport_info=transport_info,
        left_right=left_right,
        up_down=up_down,
        in_out=in_out,
        move_speed=move_speed,
        zoom_speed=zoom_speed
    )
    await safe_auth_audit(
        db,
        module="control",
        action="ptz_control",
        source="device_control",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=(
            f"channel_id={channel_id}; "
            f"lr={left_right}; ud={up_down}; io={in_out}; "
            f"move_speed={move_speed}; zoom_speed={zoom_speed}"
        ),
    )

    return {"msg": "PTZ command sent"}  # FIXED: hardcoded Chinese → English


@router.post("/{channel_id}/absolute")
async def absolute_ptz(
    channel_id: str,
    pan: float = Query(0.0, description="水平角度"),
    tilt: float = Query(0.0, description="垂直角度"),
    zoom: float = Query(1.0, description="缩放倍数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    GB/T 28181-2022 绝对云台控制
    """
    stmt = select(Resource, Asset).join(Asset, Asset.id == Resource.asset_id).where(Resource.gb_id == channel_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))

    result = await db.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Channel not found or no permission")

    resource, asset = row

    if not sip_commander:
        raise HTTPException(status_code=500, detail="SIP service not ready")

    transport_info = (
        (asset.ip_addr, asset.port),
        asset.transport or "UDP",
        sip_server.udp_transport if (asset.transport or "UDP") == "UDP" else sip_server.tcp_server
    )

    await sip_commander.send_absolute_ptz_cmd(
        device_id=asset.gb_id,
        channel_id=resource.gb_id,
        transport_info=transport_info,
        pan=pan,
        tilt=tilt,
        zoom=zoom
    )

    await safe_auth_audit(
        db,
        module="control",
        action="absolute_ptz",
        source="device_control",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"channel_id={channel_id}; pan={pan}; tilt={tilt}; zoom={zoom}",
    )

    return {"msg": "Absolute PTZ command sent"}  # FIXED: hardcoded Chinese → English

@router.post("/{channel_id}/preset")
async def control_preset(
    channel_id: str,
    cmd_type: int = Query(..., description="8:设置预置位 129:调用预置位 131:删除预置位"),
    preset_index: int = Query(..., ge=1, le=255, description="预置位编号"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    stmt = select(Resource, Asset).join(Asset, Asset.id == Resource.asset_id).where(Resource.gb_id == channel_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))

    result = await db.execute(stmt)
    row = result.first()
    if not row:
        await safe_auth_audit(
            db,
            module="control",
            action="ptz_preset_cmd",
            source="device_control",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="channel_not_found",
            extra_summary=f"channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Channel not found or no permission")

    resource, asset = row

    if not sip_commander:
        await safe_auth_audit(
            db,
            module="control",
            action="ptz_preset_cmd",
            source="device_control",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=500,
            detail="sip_commander_unavailable",
            extra_summary=f"channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="SIP service not ready")

    transport_info = (
        (asset.ip_addr, asset.port),
        asset.transport or "UDP",
        sip_server.udp_transport if (asset.transport or "UDP") == "UDP" else sip_server.tcp_server
    )

    # Preset commands:
    # Set: A5 0F 01 81 00 {preset_index} 00 {check_code} (Wait, PTZ byte 4=0x81)
    # 8 = Set, 129 = Call, 131 = Delete
    # GB28181 预置位指令格式 (A5 0F 01 cmd_code 00 preset_index 00 check_code)
    # 81=设置(129?), 82=调用(130?), 83=删除(131?) - 按行业常见兼容规则处理
    cmd_code_map = {8: 0x81, 129: 0x82, 131: 0x83}
    actual_cmd = cmd_code_map.get(cmd_type, 0x82)

    check_code = (0xA5 + 0x0F + 0x01 + actual_cmd + preset_index) % 0x100
    ptz_cmd = f"A50F01{actual_cmd:02X}00{preset_index:02X}00{check_code:02X}"

    # We can reuse the PTZ XML generation by just sending the raw Hex if we expose it
    # For now we'll add a helper in commander to send raw PTZ hex or just send it here
    # Actually let's add `send_raw_ptz_cmd` to commander
    await sip_commander.send_raw_ptz_cmd(
        device_id=asset.gb_id,
        channel_id=resource.gb_id,
        transport_info=transport_info,
        ptz_cmd=ptz_cmd
    )

    await safe_auth_audit(
        db,
        module="control",
        action="ptz_preset_cmd",
        source="device_control",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"channel_id={channel_id}; cmd_type={cmd_type}; preset_index={preset_index}",
    )

    return {"msg": "Preset command sent"}  # FIXED: hardcoded Chinese → English
