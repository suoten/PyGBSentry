from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.models.resource import Resource
from app.models.asset import Asset
# FIX: [2026-07-04] 原 `from app.sip.commander import sip_commander` 在模块加载时绑定 None，
# main.py 后续赋值 commander.sip_commander = SipCommander(...) 无法更新本模块引用，
# 导致 PTZ 端点始终返回 500 "SIP service not ready"。改为模块引用模式。 [全栈工程师]
from app.sip import commander as sip_commander_module
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
    # FIX: [2026-07-04] 原仅校验 token+is_active，无 RBAC 权限码校验，viewer 只读用户可控制云台 [全栈工程师]
    current_user: User = Depends(deps.require_permission("ptz.control"))
):
    stmt = select(Resource, Asset).join(Asset, Asset.id == Resource.asset_id).where(Resource.gb_id == channel_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))

    result = await db.execute(stmt)
    row = result.first()
    if not row:
        # FIX: [2026-07-04] GB28181 IPC设备(type=132)的device_id==channel_id，
        # 当设备未完成Catalog同步时无Resource记录，导致PTZ返回404。
        # 回退：用设备自身作为通道（device-as-channel）。 [全栈工程师]
        asset_fb_stmt = select(Asset).where(Asset.gb_id == channel_id)
        if not current_user.is_superuser:
            asset_fb_stmt = asset_fb_stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        asset = (await db.execute(asset_fb_stmt)).scalars().first()
        if not asset:
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
        resource = SimpleNamespace(
            id=asset.id,
            gb_id=asset.gb_id,
            name=asset.name,
        )
    else:
        resource, asset = row

    if not sip_commander_module.sip_commander:
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

    sent_ok = await sip_commander_module.sip_commander.send_ptz_cmd(
        device_id=asset.gb_id,
        channel_id=resource.gb_id,
        transport_info=transport_info,
        left_right=left_right,
        up_down=up_down,
        in_out=in_out,
        move_speed=move_speed,
        zoom_speed=zoom_speed
    )
    if not sent_ok:
        await safe_auth_audit(
            db,
            module="control",
            action="ptz_control",
            source="device_control",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=503,
            detail="sip_send_failed",
            extra_summary=(
                f"channel_id={channel_id}; "
                f"lr={left_right}; ud={up_down}; io={in_out}; "
                f"move_speed={move_speed}; zoom_speed={zoom_speed}"
            ),
        )
        raise HTTPException(status_code=503, detail="Failed to send PTZ command")
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

    return {"msg": "PTZ command sent"}  # i18n


@router.post("/{channel_id}/absolute")
async def absolute_ptz(
    channel_id: str,
    pan: float = Query(0.0, description="水平角度"),
    tilt: float = Query(0.0, description="垂直角度"),
    zoom: float = Query(1.0, description="缩放倍数"),
    db: AsyncSession = Depends(get_db),
    # FIX: [2026-07-04] 添加 RBAC 权限码校验 [全栈工程师]
    current_user: User = Depends(deps.require_permission("ptz.control"))
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
        # FIX: [2026-07-04] GB28181 IPC设备(type=132)的device_id==channel_id，
        # 当设备未完成Catalog同步时无Resource记录，导致PTZ返回404。
        # 回退：用设备自身作为通道（device-as-channel）。 [全栈工程师]
        asset_fb_stmt = select(Asset).where(Asset.gb_id == channel_id)
        if not current_user.is_superuser:
            asset_fb_stmt = asset_fb_stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        asset = (await db.execute(asset_fb_stmt)).scalars().first()
        if not asset:
            raise HTTPException(status_code=404, detail="Channel not found or no permission")
        resource = SimpleNamespace(
            id=asset.id,
            gb_id=asset.gb_id,
            name=asset.name,
        )
    else:
        resource, asset = row

    if not sip_commander_module.sip_commander:
        raise HTTPException(status_code=500, detail="SIP service not ready")

    transport_info = (
        (asset.ip_addr, asset.port),
        asset.transport or "UDP",
        sip_server.udp_transport if (asset.transport or "UDP") == "UDP" else sip_server.tcp_server
    )

    sent_ok = await sip_commander_module.sip_commander.send_absolute_ptz_cmd(
        device_id=asset.gb_id,
        channel_id=resource.gb_id,
        transport_info=transport_info,
        pan=pan,
        tilt=tilt,
        zoom=zoom
    )
    if not sent_ok:
        await safe_auth_audit(
            db,
            module="control",
            action="absolute_ptz",
            source="device_control",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=503,
            detail="sip_send_failed",
            extra_summary=f"channel_id={channel_id}; pan={pan}; tilt={tilt}; zoom={zoom}",
        )
        raise HTTPException(status_code=503, detail="Failed to send Absolute PTZ command")

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

    return {"msg": "Absolute PTZ command sent"}  # i18n

@router.post("/{channel_id}/preset")
async def control_preset(
    channel_id: str,
    cmd_type: int = Query(..., description="0x81=设置预置位 0x82=调用预置位 0x83=删除预置位 (兼容历史值 8=设置)"),  # FIX: [2026-07-03] 对齐 GB28181 标准字节 [全栈工程师]
    preset_index: int = Query(..., ge=1, le=255, description="预置位编号"),
    db: AsyncSession = Depends(get_db),
    # FIX: [2026-07-04] 添加 RBAC 权限码校验 [全栈工程师]
    current_user: User = Depends(deps.require_permission("ptz.control"))
):
    stmt = select(Resource, Asset).join(Asset, Asset.id == Resource.asset_id).where(Resource.gb_id == channel_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))

    result = await db.execute(stmt)
    row = result.first()
    if not row:
        # FIX: [2026-07-04] GB28181 IPC设备(type=132)的device_id==channel_id，
        # 当设备未完成Catalog同步时无Resource记录，导致PTZ返回404。
        # 回退：用设备自身作为通道（device-as-channel）。 [全栈工程师]
        asset_fb_stmt = select(Asset).where(Asset.gb_id == channel_id)
        if not current_user.is_superuser:
            asset_fb_stmt = asset_fb_stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        asset = (await db.execute(asset_fb_stmt)).scalars().first()
        if not asset:
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
        resource = SimpleNamespace(
            id=asset.id,
            gb_id=asset.gb_id,
            name=asset.name,
        )
    else:
        resource, asset = row

    if not sip_commander_module.sip_commander:
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

    # GB28181 预置位指令格式 (A5 0F 01 cmd_code 00 preset_index 00 check_code)
    # byte4 标准定义: 0x81=设置, 0x82=调用, 0x83=删除
    # FIX: [2026-07-03] 原 cmd_code_map={8:0x81,129:0x82,131:0x83} 中 129==0x81 与标准"设置"字节冲突，
    # 客户端按 GB28181 标准传 0x81(=129) 期望"设置"却得到"调用"。改为直接采用标准字节并兼容历史值 8 [全栈工程师]
    cmd_code_map = {0x81: 0x81, 0x82: 0x82, 0x83: 0x83, 8: 0x81}
    actual_cmd = cmd_code_map.get(cmd_type, 0x82)

    check_code = (0xA5 + 0x0F + 0x01 + actual_cmd + preset_index) % 0x100
    ptz_cmd = f"A50F01{actual_cmd:02X}00{preset_index:02X}00{check_code:02X}"

    # We can reuse the PTZ XML generation by just sending the raw Hex if we expose it
    # For now we'll add a helper in commander to send raw PTZ hex or just send it here
    # Actually let's add `send_raw_ptz_cmd` to commander
    sent_ok = await sip_commander_module.sip_commander.send_raw_ptz_cmd(
        device_id=asset.gb_id,
        channel_id=resource.gb_id,
        transport_info=transport_info,
        ptz_cmd=ptz_cmd
    )
    if not sent_ok:
        await safe_auth_audit(
            db,
            module="control",
            action="ptz_preset_cmd",
            source="device_control",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=503,
            detail="sip_send_failed",
            extra_summary=f"channel_id={channel_id}; cmd_type={cmd_type}; preset_index={preset_index}",
        )
        raise HTTPException(status_code=503, detail="Failed to send Preset command")

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

    return {"msg": "Preset command sent"}  # i18n


# FIX: [2026-07-04] 巡航/扫描控制 — SIP层完整实现但API层无端点暴露 [全栈工程师]
# 根因：SipPtz 类已实现 _get_cruise_cmd() / send_cruise() / _get_scan_cmd() / send_scan()，
# 但 sip_ptz 实例从未被任何 API 端点导入或调用，Commander 也无 cruise/scan 方法。
# 修复：在 API 层添加 cruise/scan 端点，复用 send_raw_ptz_cmd 发送 PTZ hex，
# hex 生成逻辑与 SipPtz._get_cruise_cmd / _get_scan_cmd 完全一致。

def _generate_cruise_hex(cruise_id: int, preset_id: int, action: str, speed: int = 128, stay_time: int = 5) -> str:
    """生成巡航控制 PTZ hex（8字节），与 SipPtz._get_cruise_cmd 逻辑一致。"""
    cruise_id = max(1, min(255, int(cruise_id)))
    preset_id = max(1, min(255, int(preset_id)))

    if action == 'add':
        cmd = [0xA5, 0x0F, 0x01, 0x82, cruise_id, preset_id, 0x00]
    elif action == 'delete':
        cmd = [0xA5, 0x0F, 0x01, 0x83, cruise_id, preset_id, 0x00]
    elif action == 'set_speed':
        speed = max(1, min(4095, int(speed)))
        speed_h = (speed >> 8) & 0xFF
        speed_l = speed & 0xFF
        cmd = [0xA5, 0x0F, 0x01, 0x84, cruise_id, speed_h, speed_l]
    elif action == 'set_time':
        stay_time = max(1, min(4095, int(stay_time)))
        time_h = (stay_time >> 8) & 0xFF
        time_l = stay_time & 0xFF
        cmd = [0xA5, 0x0F, 0x01, 0x85, cruise_id, time_h, time_l]
    elif action == 'start':
        cmd = [0xA5, 0x0F, 0x01, 0x86, cruise_id, 0x00, 0x00]
    elif action == 'stop':
        cmd = [0xA5, 0x0F, 0x01, 0x87, cruise_id, 0x00, 0x00]
    elif action == 'delete_group':
        cmd = [0xA5, 0x0F, 0x01, 0x88, cruise_id, 0x00, 0x00]
    else:
        cmd = [0xA5, 0x0F, 0x01, 0x00, 0x00, 0x00, 0x00]

    checksum = sum(cmd) % 256
    cmd.append(checksum)
    return "".join([f"{b:02X}" for b in cmd])


def _generate_scan_hex(scan_id: int, action: str, speed: int = 128) -> str:
    """生成扫描控制 PTZ hex（8字节），与 SipPtz._get_scan_cmd 逻辑一致。"""
    scan_id = max(0, min(255, int(scan_id)))

    if action == 'start':
        cmd = [0xA5, 0x0F, 0x01, 0x99, scan_id, 0x00, 0x00]
    elif action == 'stop':
        cmd = [0xA5, 0x0F, 0x01, 0x9A, scan_id, 0x00, 0x00]
    elif action == 'set_left':
        cmd = [0xA5, 0x0F, 0x01, 0x9B, scan_id, 0x00, 0x00]
    elif action == 'set_right':
        cmd = [0xA5, 0x0F, 0x01, 0x9C, scan_id, 0x00, 0x00]
    elif action == 'set_speed':
        speed = max(1, min(4095, int(speed)))
        speed_h = (speed >> 8) & 0xFF
        speed_l = speed & 0xFF
        cmd = [0xA5, 0x0F, 0x01, 0x9D, scan_id, speed_h, speed_l]
    else:
        cmd = [0xA5, 0x0F, 0x01, 0x00, 0x00, 0x00, 0x00]

    checksum = sum(cmd) % 256
    cmd.append(checksum)
    return "".join([f"{b:02X}" for b in cmd])


@router.post("/{channel_id}/cruise")
async def control_cruise(
    channel_id: str,
    action: str = Query(..., description="start/stop/add/delete/set_speed/set_time/delete_group"),
    cruise_id: int = Query(1, ge=1, le=255, description="巡航组号 1-255"),
    preset_id: int = Query(1, ge=1, le=255, description="预置位号 1-255 (add/delete 时使用)"),
    speed: int = Query(128, ge=1, le=4095, description="巡航速度 1-4095 (set_speed 时使用)"),
    stay_time: int = Query(5, ge=1, le=4095, description="停留时间秒 1-4095 (set_time 时使用)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("ptz.control")),
):
    """
    GB28181 巡航控制 — 启动/停止巡航、管理巡航组预置位、设置速度/停留时间
    """
    stmt = select(Resource, Asset).join(Asset, Asset.id == Resource.asset_id).where(Resource.gb_id == channel_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))

    result = await db.execute(stmt)
    row = result.first()
    if not row:
        asset_fb_stmt = select(Asset).where(Asset.gb_id == channel_id)
        if not current_user.is_superuser:
            asset_fb_stmt = asset_fb_stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        asset = (await db.execute(asset_fb_stmt)).scalars().first()
        if not asset:
            await safe_auth_audit(
                db,
                module="control",
                action="ptz_cruise_cmd",
                source="device_control",
                operator=current_user.username or "unknown",
                result="failed",
                tenant_id=_audit_tid(current_user),
                status_code=404,
                detail="channel_not_found",
                extra_summary=f"channel_id={channel_id}",
            )
            raise HTTPException(status_code=404, detail="Channel not found or no permission")
        resource = SimpleNamespace(id=asset.id, gb_id=asset.gb_id, name=asset.name)
    else:
        resource, asset = row

    if not sip_commander_module.sip_commander:
        await safe_auth_audit(
            db,
            module="control",
            action="ptz_cruise_cmd",
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

    ptz_cmd = _generate_cruise_hex(cruise_id, preset_id, action, speed, stay_time)

    sent_ok = await sip_commander_module.sip_commander.send_raw_ptz_cmd(
        device_id=asset.gb_id,
        channel_id=resource.gb_id,
        transport_info=transport_info,
        ptz_cmd=ptz_cmd
    )
    if not sent_ok:
        await safe_auth_audit(
            db,
            module="control",
            action="ptz_cruise_cmd",
            source="device_control",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=503,
            detail="sip_send_failed",
            extra_summary=f"channel_id={channel_id}; action={action}; cruise_id={cruise_id}",
        )
        raise HTTPException(status_code=503, detail="Failed to send Cruise command")

    await safe_auth_audit(
        db,
        module="control",
        action="ptz_cruise_cmd",
        source="device_control",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"channel_id={channel_id}; action={action}; cruise_id={cruise_id}",
    )

    return {"msg": "Cruise command sent"}  # i18n


@router.post("/{channel_id}/scan")
async def control_scan(
    channel_id: str,
    action: str = Query(..., description="start/stop/set_left/set_right/set_speed"),
    scan_id: int = Query(0, ge=0, le=255, description="扫描组号 0-255"),
    speed: int = Query(128, ge=1, le=4095, description="扫描速度 1-4095 (set_speed 时使用)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("ptz.control")),
):
    """
    GB28181 扫描控制 — 启动/停止扫描、设置左右边界、设置扫描速度
    """
    stmt = select(Resource, Asset).join(Asset, Asset.id == Resource.asset_id).where(Resource.gb_id == channel_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))

    result = await db.execute(stmt)
    row = result.first()
    if not row:
        asset_fb_stmt = select(Asset).where(Asset.gb_id == channel_id)
        if not current_user.is_superuser:
            asset_fb_stmt = asset_fb_stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        asset = (await db.execute(asset_fb_stmt)).scalars().first()
        if not asset:
            await safe_auth_audit(
                db,
                module="control",
                action="ptz_scan_cmd",
                source="device_control",
                operator=current_user.username or "unknown",
                result="failed",
                tenant_id=_audit_tid(current_user),
                status_code=404,
                detail="channel_not_found",
                extra_summary=f"channel_id={channel_id}",
            )
            raise HTTPException(status_code=404, detail="Channel not found or no permission")
        resource = SimpleNamespace(id=asset.id, gb_id=asset.gb_id, name=asset.name)
    else:
        resource, asset = row

    if not sip_commander_module.sip_commander:
        await safe_auth_audit(
            db,
            module="control",
            action="ptz_scan_cmd",
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

    ptz_cmd = _generate_scan_hex(scan_id, action, speed)

    sent_ok = await sip_commander_module.sip_commander.send_raw_ptz_cmd(
        device_id=asset.gb_id,
        channel_id=resource.gb_id,
        transport_info=transport_info,
        ptz_cmd=ptz_cmd
    )
    if not sent_ok:
        await safe_auth_audit(
            db,
            module="control",
            action="ptz_scan_cmd",
            source="device_control",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=503,
            detail="sip_send_failed",
            extra_summary=f"channel_id={channel_id}; action={action}; scan_id={scan_id}",
        )
        raise HTTPException(status_code=503, detail="Failed to send Scan command")

    await safe_auth_audit(
        db,
        module="control",
        action="ptz_scan_cmd",
        source="device_control",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"channel_id={channel_id}; action={action}; scan_id={scan_id}",
    )

    return {"msg": "Scan command sent"}  # i18n
