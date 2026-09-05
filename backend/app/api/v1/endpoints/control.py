from fastapi import Query, APIRouter, HTTPException, Depends, Body  # S-01 添加Body导入
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.api import deps
from app.api.deps import get_or_404
from app.services.auth_audit import safe_auth_audit
import app.sip.ptz as sip_ptz_module
from app.sip.server import sip_server
from pydantic import BaseModel
import json
import time

router = APIRouter()

# N-09 添加PTZ命令限速，防止淹没设备
_ptz_last_send: dict[str, float] = {}
_PTZ_RATE_LIMIT_SECONDS = 0.2  # 200ms


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


async def _control_audit(
    db: AsyncSession,
    user: User,
    *,
    action: str,
    result: str,
    status_code: int,
    detail: str,
    extra_summary: str = "",
) -> None:
    await safe_auth_audit(
        db,
        module="control",
        action=action,
        source="device_control",
        operator=user.username or "unknown",
        result=result,
        tenant_id=_audit_tid(user),
        status_code=status_code,
        detail=detail,
        extra_summary=extra_summary,
    )


class PTZRequest(BaseModel):
    command: str  # left, right, up, down, zoomin, zoomout, stop, dragzoomin, dragzoomout, absolute, focus_near, focus_far, focus_stop, iris_open, iris_close, iris_stop, preset_set, preset_goto, preset_clear, cruise_start, cruise_stop, cruise_add_preset, cruise_del_preset, cruise_set_speed, cruise_set_time, scan_start, scan_stop, scan_set_speed, scan_set_left_limit, scan_set_right_limit, wiper_on, wiper_off, aux_on, aux_off, record_start, record_stop, guard_on, guard_off, reset_alarm
    speed: int = 50
    drag_data: dict | None = None  # { "length": 720, "width": 1280, "mid_point_x": 640, "mid_point_y": 360, "length_x": 100, "length_y": 100, "preset_id": 1, "cruise_id": 1, "scan_id": 0, "aux_id": 2, "stay_time": 5 }

class PresetRequest(BaseModel):
    preset_id: int  # 1-255


class WiperRequest(BaseModel):
    command: str  # "on", "off", "stop"


class AuxSwitchRequest(BaseModel):
    aux_id: int = 2  # 2-255
    command: str  # "on", "off"


class ControlStateUpdateRequest(BaseModel):
    preset_list: list[dict] | None = None
    cruise_id: int = 1
    cruise_points: list[dict] | None = None
    cruise_speed: int | None = None
    cruise_stay_time: int | None = None
    scan_id: int = 0
    scan_speed: int | None = None

async def _get_asset_resource(db: AsyncSession, device_id: str, channel_id: str, current_user: User):
    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = get_or_404(result, detail="Asset not found")  # ORM查询结果空值判断
    stmt = select(Resource).where(Resource.gb_id == channel_id)
    if not current_user.is_superuser:
        stmt = stmt.join(Asset, Asset.id == Resource.asset_id).where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    resource = get_or_404(result, detail="Resource not found")  # ORM查询结果空值判断
    return asset, resource


def _require_sip_ptz():
    if not sip_ptz_module.sip_ptz:
        raise HTTPException(status_code=500, detail="SIP PTZ service not ready")
    return sip_ptz_module.sip_ptz


def _preset_setting_key(device_id: str, channel_id: str) -> str:
    return f"ptz:preset:{device_id}:{channel_id}"


def _cruise_setting_key(device_id: str, channel_id: str, cruise_id: int) -> str:
    return f"ptz:cruise:{device_id}:{channel_id}:{cruise_id}"


def _cruise_meta_setting_key(device_id: str, channel_id: str, cruise_id: int) -> str:
    return f"ptz:cruise_meta:{device_id}:{channel_id}:{cruise_id}"


def _scan_setting_key(device_id: str, channel_id: str, scan_id: int) -> str:
    return f"ptz:scan:{device_id}:{channel_id}:{scan_id}"


async def _load_json_setting(db: AsyncSession, key: str, default):
    result = await db.execute(select(SystemSetting).where(SystemSetting.setting_key == key))
    row = result.scalars().first()
    if not row:
        return default
    try:
        return json.loads(row.setting_value)
    except Exception:
        return default


async def _save_json_setting(db: AsyncSession, key: str, value) -> None:
    result = await db.execute(select(SystemSetting).where(SystemSetting.setting_key == key))
    row = result.scalars().first()
    encoded = json.dumps(value, ensure_ascii=False)
    if row:
        row.setting_value = encoded
    else:
        row = SystemSetting(setting_key=key, setting_value=encoded)
        db.add(row)
    await db.commit()

@router.post("/{device_id}/{channel_id}/ptz")
async def control_ptz(
    device_id: str,
    channel_id: str,
    ptz: PTZRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """云台方向/变焦/扩展控制。支持标准PTZ方向、变焦、聚焦、光圈、预置位、巡航、扫描、雨刷、辅助开关、录像、布防、报警复位等GB28181标准命令。"""
    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        await _control_audit(
            db,
            current_user,
            action="control_ptz",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not asset.ip_addr:
        await _control_audit(
            db,
            current_user,
            action="control_ptz",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network info missing")
    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _control_audit(
            db,
            current_user,
            action="control_ptz",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")
    sip_ptz = _require_sip_ptz()
    # N-09 添加PTZ命令限速，防止淹没设备
    # FIX [2026-09-04 P1]: 1) stop/focus_stop/iris_stop 是安全指令，永不限流——原实现
    #    把停止指令也按 200ms 窗口限流，429 丢弃后云台会持续转动停不下来；
    # 2) 连续移动指令在节流窗口内时静默忽略（设备本就在执行上一次移动，丢弃冗余指令
    #    是正确行为），但返回 200 而非 429——避免前端按住方向键时弹「云台控制失败」。
    now = time.monotonic()
    last_sent = _ptz_last_send.get(device_id, 0.0)
    _cmd = str(ptz.command or "").strip().lower()
    _is_stop_cmd = _cmd in {"stop", "focus_stop", "iris_stop"}
    _throttled = now - last_sent < _PTZ_RATE_LIMIT_SECONDS and not _is_stop_cmd
    if not _throttled:
        _ptz_last_send[device_id] = now
    if _throttled:
        return {"status": "ok", "action": "throttled", "command": ptz.command, "throttled": True}
    await sip_ptz.send_ptz(
        asset,
        resource,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        ptz.command,
        ptz.speed,
        drag_data=ptz.drag_data
    )
    await _control_audit(
        db,
        current_user,
        action="control_ptz",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; command={str(ptz.command)[:24]}; speed={ptz.speed}",
    )
    return {"status": "ok"}


@router.post("/{device_id}/{channel_id}/preset")
async def call_preset(
    device_id: str,
    channel_id: str,
    body: PresetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """调用预置位。preset_id 1-255。"""
    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        await _control_audit(
            db,
            current_user,
            action="call_preset",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not asset.ip_addr:
        await _control_audit(
            db,
            current_user,
            action="call_preset",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network info missing")
    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _control_audit(
            db,
            current_user,
            action="call_preset",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")
    preset_id = max(1, min(255, body.preset_id))
    sip_ptz = _require_sip_ptz()
    await sip_ptz.send_preset(asset, resource, ((asset.ip_addr, asset.port), asset.transport, transport), preset_id)
    await _control_audit(
        db,
        current_user,
        action="call_preset",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; preset_id={preset_id}",
    )
    return {"status": "ok", "preset_id": preset_id}


@router.post("/{device_id}/{channel_id}/preset/set")
async def set_preset(
    device_id: str,
    channel_id: str,
    body: PresetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """设置预置位。preset_id 1-255。"""
    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        await _control_audit(
            db,
            current_user,
            action="set_preset",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not asset.ip_addr:
        await _control_audit(
            db,
            current_user,
            action="set_preset",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network info missing")
    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _control_audit(
            db,
            current_user,
            action="set_preset",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")
    preset_id = max(1, min(255, body.preset_id))
    sip_ptz = _require_sip_ptz()
    await sip_ptz.send_preset_set(asset, resource, ((asset.ip_addr, asset.port), asset.transport, transport), preset_id)
    key = _preset_setting_key(device_id, channel_id)
    preset_list = await _load_json_setting(db, key, [])
    if not any(int(item.get("preset_id", 0)) == preset_id for item in preset_list if isinstance(item, dict)):
        preset_list.append({"preset_id": preset_id, "preset_name": str(preset_id)})
        await _save_json_setting(db, key, preset_list)
    await _control_audit(
        db,
        current_user,
        action="set_preset",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; preset_id={preset_id}",
    )
    return {"status": "ok", "preset_id": preset_id, "action": "set"}


@router.post("/{device_id}/{channel_id}/preset/delete")
async def delete_preset(
    device_id: str,
    channel_id: str,
    body: PresetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """删除预置位。preset_id 1-255。"""
    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        await _control_audit(
            db,
            current_user,
            action="delete_preset",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not asset.ip_addr:
        await _control_audit(
            db,
            current_user,
            action="delete_preset",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network info missing")
    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _control_audit(
            db,
            current_user,
            action="delete_preset",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")
    preset_id = max(1, min(255, body.preset_id))
    sip_ptz = _require_sip_ptz()
    await sip_ptz.send_preset_delete(asset, resource, ((asset.ip_addr, asset.port), asset.transport, transport), preset_id)
    key = _preset_setting_key(device_id, channel_id)
    preset_list = await _load_json_setting(db, key, [])
    preset_list = [
        item for item in preset_list
        if not (isinstance(item, dict) and int(item.get("preset_id", 0)) == preset_id)
    ]
    await _save_json_setting(db, key, preset_list)
    await _control_audit(
        db,
        current_user,
        action="delete_preset",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; preset_id={preset_id}",
    )
    return {"status": "ok", "preset_id": preset_id, "action": "delete"}


@router.get("/{device_id}/{channel_id}/preset/query")
async def query_preset(
    device_id: str,
    channel_id: str,
    remote: bool = Query(False, description="Query from device via SIP PresetQuery command"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Query preset position list.

    By default returns locally maintained preset list.
    Set remote=true to send PresetQuery command to device via SIP.
    """
    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        raise HTTPException(status_code=404, detail="Device or channel not found")

    # 支持向设备发送PresetQuery命令查询预置位，与wvp对齐
    if remote:
        if not asset.ip_addr:
            raise HTTPException(status_code=500, detail="Device network information missing")
        transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
        if transport is None:
            raise HTTPException(status_code=503, detail="Device signaling transport unavailable")
        import app.sip.commander as sip_commander_module
        if not getattr(sip_commander_module, "sip_commander", None):
            raise HTTPException(status_code=503, detail="SIP service not ready")
        sn = await sip_commander_module.sip_commander.send_preset_query(
            device_id=asset.gb_id,
            channel_id=resource.gb_id,
            transport_info=((asset.ip_addr, asset.port), asset.transport, transport),
        )
        return {
            "status": "ok",
            "device_id": device_id,
            "channel_id": channel_id,
            "sn": sn,
            "message": "PresetQuery command sent to device, response will be processed asynchronously",
        }

    key = _preset_setting_key(device_id, channel_id)
    preset_list = await _load_json_setting(db, key, [])
    return {
        "status": "ok",
        "device_id": device_id,
        "channel_id": channel_id,
        "preset_range": {"min": 1, "max": 255},
        "preset_list": preset_list,
    }


@router.get("/{device_id}/{channel_id}/preset/list")
async def list_preset(
    device_id: str,
    channel_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """查询本地维护的预置位列表。"""
    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        raise HTTPException(status_code=404, detail="Device or channel not found")
    key = _preset_setting_key(device_id, channel_id)
    preset_list = await _load_json_setting(db, key, [])
    return {"status": "ok", "device_id": device_id, "channel_id": channel_id, "preset_list": preset_list}


# ==================== 设备控制接口 ====================

class GuardRequest(BaseModel):
    """布防/撤防请求"""
    guard_cmd: str  # "SetGuard" 或 "ResetGuard"


class RecordControlRequest(BaseModel):
    """录像控制请求"""
    record_cmd: str  # "Record" 或 "StopRecord"


class AlarmResetRequest(BaseModel):
    """报警复位请求"""
    alarm_method: str = ""
    alarm_type: str = ""


class DragZoomRequest(BaseModel):
    """框选缩放请求"""  # GB28181 DragZoom框选缩放 — API请求模型
    zoom_cmd: str  # "DragZoomIn" 或 "DragZoomOut"
    left_top_x: int  # 框选左上角X坐标
    left_top_y: int  # 框选左上角Y坐标
    right_bottom_x: int  # 框选右下角X坐标
    right_bottom_y: int  # 框选右下角Y坐标


@router.post("/{device_id}/{channel_id}/guard")
async def device_guard(
    device_id: str,
    channel_id: str,
    body: GuardRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """布防/撤防控制。guard_cmd: SetGuard(布防) / ResetGuard(撤防)"""
    from app.sip.device_control import device_control

    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        await _control_audit(
            db,
            current_user,
            action="device_guard",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not asset.ip_addr:
        await _control_audit(
            db,
            current_user,
            action="device_guard",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network info missing")

    # Validate guard_cmd
    if body.guard_cmd not in ["SetGuard", "ResetGuard"]:
        await _control_audit(
            db,
            current_user,
            action="device_guard",
            result="failed",
            status_code=400,
            detail="invalid_guard_cmd",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail="guard_cmd must be SetGuard or ResetGuard")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _control_audit(
            db,
            current_user,
            action="device_guard",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    await device_control.send_guard(
        asset, resource.gb_id,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        body.guard_cmd
    )

    action = "SetGuard" if body.guard_cmd == "SetGuard" else "ResetGuard"  # W-19 中文→英文
    await _control_audit(
        db,
        current_user,
        action="device_guard",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; guard_cmd={body.guard_cmd}",
    )
    return {"status": "ok", "action": action, "guard_cmd": body.guard_cmd}


@router.post("/{device_id}/teleboot")
async def device_teleboot(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """远程重启设备"""
    from app.sip.device_control import device_control

    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        tenant_id = current_user.tenant_id or "default"
        stmt = stmt.where(Asset.tenant_id == tenant_id)
    result = await db.execute(stmt)
    asset = result.scalars().first()

    if not asset:
        await _control_audit(
            db,
            current_user,
            action="device_teleboot",
            result="failed",
            status_code=404,
            detail="device_not_found",
            extra_summary=f"device_id={device_id}",
        )
        raise HTTPException(status_code=404, detail="Device not found")
    if not asset.ip_addr:
        await _control_audit(
            db,
            current_user,
            action="device_teleboot",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}",
        )
        raise HTTPException(status_code=500, detail="Device network info missing")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _control_audit(
            db,
            current_user,
            action="device_teleboot",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={device_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    await device_control.send_teleboot(
        asset,
        ((asset.ip_addr, asset.port), asset.transport, transport)
    )

    await _control_audit(
        db,
        current_user,
        action="device_teleboot",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}",
    )
    return {"status": "ok", "action": "remote reboot", "device_id": device_id}  # i18n


@router.post("/{device_id}/{channel_id}/record")
async def device_record_control(
    device_id: str,
    channel_id: str,
    body: RecordControlRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """录像控制。record_cmd: Record(开始录像) / StopRecord(停止录像)"""
    from app.sip.device_control import device_control

    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        await _control_audit(
            db,
            current_user,
            action="device_record_control",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not asset.ip_addr:
        await _control_audit(
            db,
            current_user,
            action="device_record_control",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network info missing")

    # Validate record_cmd
    if body.record_cmd not in ["Record", "StopRecord"]:
        await _control_audit(
            db,
            current_user,
            action="device_record_control",
            result="failed",
            status_code=400,
            detail="invalid_record_cmd",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail="record_cmd must be Record or StopRecord")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _control_audit(
            db,
            current_user,
            action="device_record_control",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    await device_control.send_record_control(
        asset, resource.gb_id,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        body.record_cmd
    )

    action = "StartRecord" if body.record_cmd == "Record" else "StopRecord"  # W-19 中文→英文
    await _control_audit(
        db,
        current_user,
        action="device_record_control",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; record_cmd={body.record_cmd}",
    )
    return {"status": "ok", "action": action, "record_cmd": body.record_cmd}


@router.post("/{device_id}/{channel_id}/alarm-reset")
async def device_alarm_reset(
    device_id: str,
    channel_id: str,
    body: AlarmResetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """报警复位"""
    from app.sip.device_control import device_control

    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        await _control_audit(
            db,
            current_user,
            action="device_alarm_reset",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not asset.ip_addr:
        await _control_audit(
            db,
            current_user,
            action="device_alarm_reset",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network info missing")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _control_audit(
            db,
            current_user,
            action="device_alarm_reset",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    await device_control.send_alarm_reset(
        asset, resource.gb_id,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        body.alarm_method,
        body.alarm_type
    )

    await _control_audit(
        db,
        current_user,
        action="device_alarm_reset",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}",
    )
    return {"status": "ok", "action": "alarm reset"}  # i18n


@router.post("/{device_id}/{channel_id}/drag-zoom")
async def device_drag_zoom(
    device_id: str,
    channel_id: str,
    body: DragZoomRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """框选缩放控制。zoom_cmd: DragZoomIn(框选放大) / DragZoomOut(框选缩小)"""
    # GB28181 DragZoom框选缩放 — API端点
    from app.sip.device_control import device_control

    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        await _control_audit(
            db,
            current_user,
            action="device_drag_zoom",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not asset.ip_addr:
        await _control_audit(
            db,
            current_user,
            action="device_drag_zoom",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network info missing")

    # Validate zoom_cmd
    if body.zoom_cmd not in ["DragZoomIn", "DragZoomOut"]:
        await _control_audit(
            db,
            current_user,
            action="device_drag_zoom",
            result="failed",
            status_code=400,
            detail="invalid_zoom_cmd",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail="zoom_cmd must be DragZoomIn or DragZoomOut")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _control_audit(
            db,
            current_user,
            action="device_drag_zoom",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    await device_control.send_drag_zoom(
        asset, resource.gb_id,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        body.zoom_cmd,
        body.left_top_x, body.left_top_y,
        body.right_bottom_x, body.right_bottom_y,
    )

    action = "DragZoomIn" if body.zoom_cmd == "DragZoomIn" else "DragZoomOut"  # W-19 中文→英文
    await _control_audit(
        db,
        current_user,
        action="device_drag_zoom",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; zoom_cmd={body.zoom_cmd}",
    )
    return {"status": "ok", "action": action, "zoom_cmd": body.zoom_cmd}


@router.post("/{device_id}/{channel_id}/iframe")
async def device_iframe_request(
    device_id: str,
    channel_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """强制关键帧"""
    from app.sip.device_control import device_control

    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        await _control_audit(
            db,
            current_user,
            action="device_iframe_request",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not asset.ip_addr:
        await _control_audit(
            db,
            current_user,
            action="device_iframe_request",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network info missing")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _control_audit(
            db,
            current_user,
            action="device_iframe_request",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    await device_control.send_iframe_request(
        asset, resource.gb_id,
        ((asset.ip_addr, asset.port), asset.transport, transport)
    )

    await _control_audit(
        db,
        current_user,
        action="device_iframe_request",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}",
    )
    return {"status": "ok", "action": "force keyframe"}  # i18n


# ==================== 看守位控制接口 ====================

class HomePositionRequest(BaseModel):
    """看守位控制请求"""
    enabled: bool = True
    preset_index: int = 1  # 1-255
    reset_time: int = 5  # seconds


@router.post("/{device_id}/{channel_id}/home-position")
async def device_home_position(
    device_id: str,
    channel_id: str,
    body: HomePositionRequest = Body(default=HomePositionRequest()),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """看守位控制"""
    from app.sip.device_control import device_control

    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        raise HTTPException(status_code=404, detail="Device or channel not found")

    if not sip_server:  # S-01 直接使用模块级sip_server，移除未定义的_get_sip_server()
        raise HTTPException(status_code=503, detail="SIP server not ready")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    await device_control.send_home_position(
        asset, resource.gb_id,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        enabled=body.enabled,
        preset_index=body.preset_index,
        reset_time=body.reset_time,
    )

    action = "enable home position" if body.enabled else "disable home position"
    await _control_audit(
        db,
        current_user,
        action="device_home_position",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; enabled={body.enabled}; preset={body.preset_index}",
    )
    return {"status": "ok", "action": action, "preset_index": body.preset_index, "reset_time": body.reset_time}


# ==================== 光圈/聚焦控制接口 ====================

class IrisRequest(BaseModel):
    """光圈控制请求"""
    command: str  # "in"(光圈大), "out"(光圈小), "stop"
    speed: int = 128  # 0-255


class FocusRequest(BaseModel):
    """聚焦控制请求"""
    command: str  # "near"(近焦), "far"(远焦), "stop"
    speed: int = 128  # 0-255


@router.post("/{device_id}/{channel_id}/iris")
async def control_iris(
    device_id: str,
    channel_id: str,
    body: IrisRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """光圈控制。command: in(光圈大) / out(光圈小) / stop"""
    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        await _control_audit(
            db,
            current_user,
            action="control_iris",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not asset.ip_addr:
        await _control_audit(
            db,
            current_user,
            action="control_iris",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network info missing")

    # Validate command
    if body.command not in ["in", "out", "stop"]:
        await _control_audit(
            db,
            current_user,
            action="control_iris",
            result="failed",
            status_code=400,
            detail="invalid_command",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail="command must be in, out or stop")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _control_audit(
            db,
            current_user,
            action="control_iris",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    sip_ptz = _require_sip_ptz()
    await sip_ptz.send_iris(
        asset, resource,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        body.command, body.speed
    )

    action_map = {"in": "IrisOpen", "out": "IrisClose", "stop": "IrisStop"}  # W-19 中文→英文
    await _control_audit(
        db,
        current_user,
        action="control_iris",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; command={body.command}",
    )
    return {"status": "ok", "action": action_map[body.command], "command": body.command}


@router.post("/{device_id}/{channel_id}/focus")
async def control_focus(
    device_id: str,
    channel_id: str,
    body: FocusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """聚焦控制。command: near(近焦) / far(远焦) / stop"""
    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        await _control_audit(
            db,
            current_user,
            action="control_focus",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not asset.ip_addr:
        await _control_audit(
            db,
            current_user,
            action="control_focus",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network info missing")

    # Validate command
    if body.command not in ["near", "far", "stop"]:
        await _control_audit(
            db,
            current_user,
            action="control_focus",
            result="failed",
            status_code=400,
            detail="invalid_command",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail="command must be near, far or stop")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _control_audit(
            db,
            current_user,
            action="control_focus",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    sip_ptz = _require_sip_ptz()
    await sip_ptz.send_focus(
        asset, resource,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        body.command, body.speed
    )

    action_map = {"near": "FocusNear", "far": "FocusFar", "stop": "FocusStop"}  # W-19 中文→英文
    await _control_audit(
        db,
        current_user,
        action="control_focus",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; command={body.command}",
    )
    return {"status": "ok", "action": action_map[body.command], "command": body.command}


# ==================== 巡航/扫描控制接口 ====================

class CruiseRequest(BaseModel):
    """巡航控制请求"""
    cruise_id: int  # 巡航组号 1-255
    preset_id: int = 1  # 预置位号 1-255
    action: str  # "add", "delete", "set_speed", "set_time", "start", "stop", "delete_group"
    speed: int = 128  # 巡航速度 1-4095
    stay_time: int = 5  # 停留时间 1-4095 (秒)


class ScanRequest(BaseModel):
    """扫描控制请求"""
    scan_id: int  # 扫描组号 0-255
    action: str  # "start", "stop", "set_left", "set_right", "set_speed"
    speed: int = 128  # 扫描速度 1-4095


@router.post("/{device_id}/{channel_id}/cruise")
async def control_cruise(
    device_id: str,
    channel_id: str,
    body: CruiseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """巡航控制。action: add/delete/set_speed/set_time/start/stop/delete_group"""
    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        await _control_audit(
            db,
            current_user,
            action="control_cruise",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not asset.ip_addr:
        await _control_audit(
            db,
            current_user,
            action="control_cruise",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network info missing")

    # Validate action
    valid_actions = ["add", "delete", "set_speed", "set_time", "start", "stop", "delete_group"]
    if body.action not in valid_actions:
        await _control_audit(
            db,
            current_user,
            action="control_cruise",
            result="failed",
            status_code=400,
            detail="invalid_action",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail=f"action must be one of {valid_actions}")  # i18n

    # Validate cruise_id and preset_id
    if not (1 <= body.cruise_id <= 255):
        await _control_audit(
            db,
            current_user,
            action="control_cruise",
            result="failed",
            status_code=400,
            detail="invalid_cruise_id",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail="cruise_id must be between 1 and 255")
    # preset_id 仅在 add/delete 时强依赖；其余动作允许默认值
    if body.action in ["add", "delete"] and not (1 <= body.preset_id <= 255):
        await _control_audit(
            db,
            current_user,
            action="control_cruise",
            result="failed",
            status_code=400,
            detail="invalid_preset_id",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail="preset_id must be between 1-255 for add/delete operations")  # i18n

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _control_audit(
            db,
            current_user,
            action="control_cruise",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    sip_ptz = _require_sip_ptz()
    await sip_ptz.send_cruise(
        asset, resource,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        body.cruise_id, body.preset_id, body.action, body.speed, body.stay_time
    )
    key = _cruise_setting_key(device_id, channel_id, body.cruise_id)
    cruise_points = await _load_json_setting(db, key, [])
    if body.action == "add":
        exists = any(int(item.get("preset_id", 0)) == body.preset_id for item in cruise_points if isinstance(item, dict))
        if not exists:
            cruise_points.append({"preset_id": body.preset_id, "preset_name": str(body.preset_id)})
            await _save_json_setting(db, key, cruise_points)
    elif body.action == "delete":
        cruise_points = [
            item for item in cruise_points
            if not (isinstance(item, dict) and int(item.get("preset_id", 0)) == body.preset_id)
        ]
        await _save_json_setting(db, key, cruise_points)
    elif body.action == "delete_group":
        await _save_json_setting(db, key, [])
    if body.action in ["set_speed", "set_time"]:
        meta_key = _cruise_meta_setting_key(device_id, channel_id, body.cruise_id)
        current_meta = await _load_json_setting(db, meta_key, {"speed": 128, "stay_time": 5})
        if body.action == "set_speed":
            current_meta["speed"] = int(body.speed)
        if body.action == "set_time":
            current_meta["stay_time"] = int(body.stay_time)
        await _save_json_setting(db, meta_key, current_meta)

    action_map = {  # W-19 中文→英文
        "add": "AddCruisePoint",
        "delete": "DeleteCruisePoint",
        "set_speed": "SetCruiseSpeed",
        "set_time": "SetCruiseStayTime",
        "start": "StartCruise",
        "stop": "StopCruise",
        "delete_group": "DeleteCruiseGroup"
    }
    await _control_audit(
        db,
        current_user,
        action="control_cruise",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; cruise_action={body.action}; cruise_id={body.cruise_id}",
    )
    return {
        "status": "ok",
        "action": action_map[body.action],
        "cruise_id": body.cruise_id,
        "preset_id": body.preset_id
    }


@router.get("/{device_id}/{channel_id}/cruise/{cruise_id}/points")
async def get_cruise_points(
    device_id: str,
    channel_id: str,
    cruise_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """查询本地维护的巡航组点位。"""
    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not (1 <= cruise_id <= 255):
        raise HTTPException(status_code=400, detail="cruise_id must be between 1 and 255")
    key = _cruise_setting_key(device_id, channel_id, cruise_id)
    points = await _load_json_setting(db, key, [])
    meta_key = _cruise_meta_setting_key(device_id, channel_id, cruise_id)
    cruise_meta = await _load_json_setting(db, meta_key, {"speed": 128, "stay_time": 5})
    return {
        "status": "ok",
        "device_id": device_id,
        "channel_id": channel_id,
        "cruise_id": cruise_id,
        "points": points,
        "speed": int(cruise_meta.get("speed", 128)),
        "stay_time": int(cruise_meta.get("stay_time", 5)),
    }


@router.post("/{device_id}/{channel_id}/scan")
async def control_scan(
    device_id: str,
    channel_id: str,
    body: ScanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """扫描控制。action: start(开始扫描) / stop(停止扫描) / set_left(设置左边界) / set_right(设置右边界) / set_speed(设置速度)"""
    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        await _control_audit(
            db,
            current_user,
            action="control_scan",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not asset.ip_addr:
        await _control_audit(
            db,
            current_user,
            action="control_scan",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network info missing")

    # Validate action
    valid_actions = ["start", "stop", "set_left", "set_right", "set_speed"]
    if body.action not in valid_actions:
        await _control_audit(
            db,
            current_user,
            action="control_scan",
            result="failed",
            status_code=400,
            detail="invalid_action",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail=f"action must be one of {valid_actions}")  # i18n

    # Validate scan_id
    if not (0 <= body.scan_id <= 255):
        await _control_audit(
            db,
            current_user,
            action="control_scan",
            result="failed",
            status_code=400,
            detail="invalid_scan_id",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail="scan_id must be between 0 and 255")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _control_audit(
            db,
            current_user,
            action="control_scan",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    sip_ptz = _require_sip_ptz()
    await sip_ptz.send_scan(
        asset, resource,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        body.scan_id, body.action, body.speed
    )
    if body.action == "set_speed":
        scan_key = _scan_setting_key(device_id, channel_id, body.scan_id)
        await _save_json_setting(db, scan_key, {"scan_id": body.scan_id, "speed": int(body.speed)})

    action_map = {  # W-19 中文→英文
        "start": "StartScan",
        "stop": "StopScan",
        "set_left": "SetScanLeftLimit",
        "set_right": "SetScanRightLimit",
        "set_speed": "SetScanSpeed"
    }
    await _control_audit(
        db,
        current_user,
        action="control_scan",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; scan_action={body.action}; scan_id={body.scan_id}",
    )
    return {
        "status": "ok",
        "action": action_map[body.action],
        "scan_id": body.scan_id
    }


@router.get("/{device_id}/{channel_id}/scan/{scan_id}/config")
async def get_scan_config(
    device_id: str,
    channel_id: str,
    scan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """查询本地维护的扫描配置（当前主要包含扫描速度）。"""
    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not (0 <= scan_id <= 255):
        raise HTTPException(status_code=400, detail="scan_id must be between 0 and 255")
    scan_key = _scan_setting_key(device_id, channel_id, scan_id)
    cfg = await _load_json_setting(db, scan_key, {"scan_id": scan_id, "speed": 128})
    return {
        "status": "ok",
        "device_id": device_id,
        "channel_id": channel_id,
        "scan_id": scan_id,
        "speed": int(cfg.get("speed", 128)),
    }


@router.get("/{device_id}/{channel_id}/state")
async def get_control_state(
    device_id: str,
    channel_id: str,
    cruise_id: int = Query(1, ge=1),
    scan_id: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """聚合查询云台状态（预置位、巡航组点位与参数、扫描参数）。"""
    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not (1 <= cruise_id <= 255):
        raise HTTPException(status_code=400, detail="cruise_id must be between 1 and 255")
    if not (0 <= scan_id <= 255):
        raise HTTPException(status_code=400, detail="scan_id must be between 0 and 255")

    preset_key = _preset_setting_key(device_id, channel_id)
    preset_list = await _load_json_setting(db, preset_key, [])

    cruise_key = _cruise_setting_key(device_id, channel_id, cruise_id)
    cruise_points = await _load_json_setting(db, cruise_key, [])
    cruise_meta_key = _cruise_meta_setting_key(device_id, channel_id, cruise_id)
    cruise_meta = await _load_json_setting(db, cruise_meta_key, {"speed": 128, "stay_time": 5})

    scan_key = _scan_setting_key(device_id, channel_id, scan_id)
    scan_cfg = await _load_json_setting(db, scan_key, {"scan_id": scan_id, "speed": 128})

    return {
        "status": "ok",
        "device_id": device_id,
        "channel_id": channel_id,
        "preset_list": preset_list,
        "cruise": {
            "cruise_id": cruise_id,
            "points": cruise_points,
            "speed": int(cruise_meta.get("speed", 128)),
            "stay_time": int(cruise_meta.get("stay_time", 5)),
        },
        "scan": {
            "scan_id": scan_id,
            "speed": int(scan_cfg.get("speed", 128)),
        },
    }


@router.post("/{device_id}/{channel_id}/state")
async def update_control_state(
    device_id: str,
    channel_id: str,
    body: ControlStateUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """批量更新云台状态缓存（预置位/巡航/扫描）。"""
    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        await _control_audit(
            db,
            current_user,
            action="update_control_state_cache",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not (1 <= body.cruise_id <= 255):
        await _control_audit(
            db,
            current_user,
            action="update_control_state_cache",
            result="failed",
            status_code=400,
            detail="invalid_cruise_id",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail="cruise_id must be between 1 and 255")
    if not (0 <= body.scan_id <= 255):
        await _control_audit(
            db,
            current_user,
            action="update_control_state_cache",
            result="failed",
            status_code=400,
            detail="invalid_scan_id",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail="scan_id must be between 0 and 255")

    if body.preset_list is not None:
        normalized_presets = []
        for item in body.preset_list:
            if not isinstance(item, dict):
                continue
            pid = int(item.get("preset_id", 0) or 0)
            if 1 <= pid <= 255:
                normalized_presets.append({"preset_id": pid, "preset_name": str(item.get("preset_name") or pid)})
        await _save_json_setting(db, _preset_setting_key(device_id, channel_id), normalized_presets)

    if body.cruise_points is not None:
        normalized_points = []
        for item in body.cruise_points:
            if not isinstance(item, dict):
                continue
            pid = int(item.get("preset_id", 0) or 0)
            if 1 <= pid <= 255:
                normalized_points.append({"preset_id": pid, "preset_name": str(item.get("preset_name") or pid)})
        await _save_json_setting(db, _cruise_setting_key(device_id, channel_id, body.cruise_id), normalized_points)

    if body.cruise_speed is not None or body.cruise_stay_time is not None:
        meta_key = _cruise_meta_setting_key(device_id, channel_id, body.cruise_id)
        current_meta = await _load_json_setting(db, meta_key, {"speed": 128, "stay_time": 5})
        if body.cruise_speed is not None:
            current_meta["speed"] = max(1, min(4095, int(body.cruise_speed)))
        if body.cruise_stay_time is not None:
            current_meta["stay_time"] = max(1, min(4095, int(body.cruise_stay_time)))
        await _save_json_setting(db, meta_key, current_meta)

    if body.scan_speed is not None:
        await _save_json_setting(
            db,
            _scan_setting_key(device_id, channel_id, body.scan_id),
            {"scan_id": body.scan_id, "speed": max(1, min(4095, int(body.scan_speed)))},
        )

    await _control_audit(
        db,
        current_user,
        action="update_control_state_cache",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; cruise_id={body.cruise_id}; scan_id={body.scan_id}",
    )
    return {"status": "ok"}


@router.post("/{device_id}/{channel_id}/wiper")
async def control_wiper(
    device_id: str,
    channel_id: str,
    body: WiperRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """雨刷控制。command: on / off / stop"""
    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        await _control_audit(
            db,
            current_user,
            action="control_wiper",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not asset.ip_addr:
        await _control_audit(
            db,
            current_user,
            action="control_wiper",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network info missing")
    if body.command not in ["on", "off", "stop"]:
        await _control_audit(
            db,
            current_user,
            action="control_wiper",
            result="failed",
            status_code=400,
            detail="invalid_command",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail="command must be on, off or stop")
    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _control_audit(
            db,
            current_user,
            action="control_wiper",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")
    sip_ptz = _require_sip_ptz()
    await sip_ptz.send_wiper(
        asset, resource,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        body.command
    )
    action_map = {"on": "WiperOn", "off": "WiperOff", "stop": "WiperStop"}  # W-13 中文action→英文
    await _control_audit(
        db,
        current_user,
        action="control_wiper",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; command={body.command}",
    )
    return {"status": "ok", "action": action_map[body.command], "command": body.command}


@router.post("/{device_id}/{channel_id}/aux")
async def control_aux_switch(
    device_id: str,
    channel_id: str,
    body: AuxSwitchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """辅助开关控制。command: on / off, aux_id: 2-255"""
    asset, resource = await _get_asset_resource(db, device_id, channel_id, current_user)
    if not asset or not resource:
        await _control_audit(
            db,
            current_user,
            action="control_aux_switch",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")
    if not asset.ip_addr:
        await _control_audit(
            db,
            current_user,
            action="control_aux_switch",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network info missing")
    if body.command not in ["on", "off"]:
        await _control_audit(
            db,
            current_user,
            action="control_aux_switch",
            result="failed",
            status_code=400,
            detail="invalid_command",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail="command must be on or off")
    if not (2 <= body.aux_id <= 255):
        await _control_audit(
            db,
            current_user,
            action="control_aux_switch",
            result="failed",
            status_code=400,
            detail="invalid_aux_id",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail="aux_id must be between 2 and 255")
    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _control_audit(
            db,
            current_user,
            action="control_aux_switch",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")
    sip_ptz = _require_sip_ptz()
    await sip_ptz.send_aux_switch(
        asset, resource,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        body.aux_id, body.command
    )
    action = "AuxSwitchOn" if body.command == "on" else "AuxSwitchOff"  # W-13 中文action→英文
    await _control_audit(
        db,
        current_user,
        action="control_aux_switch",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; aux_id={body.aux_id}; command={body.command}",
    )
    return {"status": "ok", "action": action, "aux_id": body.aux_id, "command": body.command}
