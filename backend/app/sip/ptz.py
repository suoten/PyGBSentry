from app.sip.message import SipMessage
from xml.sax.saxutils import escape as _xml_escape
from app.core.config import settings, sip_host_for_contact
from app.sip.trace_events import should_warn_unknown_event_once
from app.services.sip_trace_store import schedule_store_sip_trace
from app.sip.send import send_sip_bytes
from loguru import logger
import random
import time
import itertools
import asyncio

# GB28181协议 — PTZ指令限流器，防止SIP消息洪泛
import time as _ptz_time

class _PtzRateLimiter:
    """Per-device PTZ command rate limiter with latest-command-priority strategy."""
    def __init__(self, min_interval: float = 0.1):
        self._min_interval = min_interval
        self._last_send: dict[str, float] = {}  # device_id -> last_send_time
        self._cancelled: set[str] = set()  # PTZ最新指令优先策略 — 被取消的device_id集合

    def cancel_pending(self, device_id: str) -> None:
        """Mark a device's pending command as cancelled so the next acquire skips it."""
        self._cancelled.add(device_id)  # PTZ最新指令优先策略 — 新指令到达时取消旧指令

    async def acquire(self, device_id: str) -> bool:
        """Acquire rate limit slot. Returns False if this command was superseded by a newer one."""
        now = _ptz_time.monotonic()
        last = self._last_send.get(device_id, 0)
        wait = self._min_interval - (now - last)
        if wait > 0:
            # PTZ最新指令优先策略 — 等待前检查是否已被新指令取消
            if device_id in self._cancelled:
                self._cancelled.discard(device_id)
                logger.debug(f"PTZ rate limiter: command for {device_id} cancelled by newer command")
                return False
            await asyncio.sleep(wait)
            # PTZ最新指令优先策略 — 等待后再次检查是否已被新指令取消
            if device_id in self._cancelled:
                self._cancelled.discard(device_id)
                logger.debug(f"PTZ rate limiter: command for {device_id} cancelled by newer command after wait")
                return False
        self._last_send[device_id] = _ptz_time.monotonic()
        return True

_ptz_rate_limiter = _PtzRateLimiter(min_interval=float(getattr(settings, "PTZ_MIN_INTERVAL_SECONDS", 0.1) or 0.1))

# SN序列号使用递增计数器替代随机数
_sn_counter = itertools.count(10001)

def _next_sn() -> int:
    return next(_sn_counter)


def _attach_trace_header(req: SipMessage) -> None:
    call_id = (req.get_header("Call-ID") or "").strip()
    if call_id:
        req.headers["X-Trace-ID"] = call_id


def _sip_trace_should_log() -> bool:
    if not bool(getattr(settings, "SIP_DEBUG_TRACE_ENABLED", False)):
        return False
    try:
        rate = float(getattr(settings, "SIP_TRACE_SAMPLE_RATE", 1.0) or 1.0)
    except Exception:
        logger.warning("SIP_TRACE_SAMPLE_RATE config parse failed")  # 国际化
        rate = 1.0
    rate = max(0.0, min(1.0, rate))
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() < rate


def _sip_trace_log(event: str, **fields):
    if not _sip_trace_should_log():
        return
    if should_warn_unknown_event_once(event):
        logger.warning(f"SIP_TRACE event not registered in trace_events.py: {event}")
    payload = {"event": event}
    payload.update(fields)
    logger.info(f"SIP_TRACE {payload}")
    schedule_store_sip_trace(payload)

class SipPtz:
    def __init__(self, sip_server):
        self.sip_server = sip_server

    def _get_ptz_cmd(self, cmd_code: int, param1: int, parameter2: int, combine_code2: int) -> str:
        """
        Generate PTZ Command String (A5 0F 01 ...)
        """
        # Header A5 0F 01
        # CmdCode
        # Param1 (Horizontal Speed)
        # Param2 (Vertical Speed)
        # CombineCode2 (Zoom Speed & Checksum)
        
        cmd = [0xA5, 0x0F, 0x01, cmd_code, param1, parameter2, combine_code2 & 0xF0]
        
        # Checksum: (A5+0F+01+CmdCode+Param1+Param2+CombineCode2)%256
        checksum = sum(cmd) % 256
        cmd.append(checksum)
        
        return "".join([f"{b:02X}" for b in cmd])

    async def _send_device_control_xml(self, asset, channel_id: str, transport_info: tuple, xml_body: str, call_suffix: str, log_label: str):
        """Send generic DeviceControl MESSAGE."""
        addr, proto, transport = transport_info
        sn = _next_sn()  # SN序列号使用递增计数器替代hash
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{asset.gb_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch=z9hG4bK{sn}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={sn}"
        req.headers["To"] = f"<sip:{asset.gb_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_{call_suffix}@{sip_host_for_contact()}"
        req.headers["CSeq"] = "1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        req.body = xml_body
        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)
        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent {log_label} to {channel_id}")
        return trace_id, proto, addr

    async def send_ptz(self, asset, resource, transport_info: tuple, command: str, speed: int = 50, drag_data: dict = None):
        """Send PTZ Control Message - supports standard PTZ and DragZoom 3D positioning."""
        addr, proto, transport = transport_info
        device_id = asset.gb_id
        channel_id = resource.gb_id
        _ptz_rate_limiter.cancel_pending(device_id)  # PTZ最新指令优先策略 — 新指令取消旧指令
        if not await _ptz_rate_limiter.acquire(device_id):  # PTZ最新指令优先策略 — 被新指令取代则跳过
            return
        
        # SN序列号使用递增计数器替代随机数
        sn = _next_sn()
        xml_body = ""
        
        # 3D 放大/定位 (DragZoom - GB/T 28181-2022 & 2016 扩展)
        if command in ("dragzoomin", "dragzoomout") and drag_data:
            length = drag_data.get("length", 720)
            width = drag_data.get("width", 1280)
            mid_point_x = drag_data.get("midPointX", 640)
            mid_point_y = drag_data.get("midPointY", 360)
            length_x = drag_data.get("lengthX", 100)
            length_y = drag_data.get("lengthY", 100)
            cmd_type = "DragZoomIn" if command == "dragzoomin" else "DragZoomOut"
            
            xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<{cmd_type}>
<Length>{length}</Length>
<Width>{width}</Width>
<MidPointX>{mid_point_x}</MidPointX>
<MidPointY>{mid_point_y}</MidPointY>
<LengthX>{length_x}</LengthX>
<LengthY>{length_y}</LengthY>
</{cmd_type}>
</Control>
"""
        elif command == "absolute":
            # GB/T 28181-2022 绝对云台控制 (Absolute PTZ)
            # drag_data 包含 pan, tilt, zoom 信息
            pan = drag_data.get("pan", 0)
            tilt = drag_data.get("tilt", 0)
            zoom = drag_data.get("zoom", 1)
            xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<PTZCmd>
<Pan>{pan}</Pan>
<Tilt>{tilt}</Tilt>
<Zoom>{zoom}</Zoom>
</PTZCmd>
</Control>
"""
        else:
            # Map command to GB28181 CmdCode
            # GB4 PTZ扩展命令 — GB28181标准命令集
            cmd_code = 0x00
            param1 = 0 # Pan Speed
            param2 = 0 # Tilt Speed
            combine_code2 = 0 # Zoom Speed (High 4 bits)

            if command == "stop":
                logger.debug("PTZ stop command received, sending zero-velocity stop")  # PTZ stop 命令为空操作
            elif command == "right":
                cmd_code = 0x01
                param1 = speed
            elif command == "left":
                cmd_code = 0x02
                param1 = speed
            elif command == "down":
                cmd_code = 0x04
                param2 = speed
            elif command == "up":
                cmd_code = 0x08
                param2 = speed
            elif command == "zoomin":
                cmd_code = 0x10
                combine_code2 = (speed & 0x0F) << 4
            elif command == "zoomout":
                cmd_code = 0x20
                combine_code2 = (speed & 0x0F) << 4
            # GB4 PTZ扩展命令 — 聚焦控制
            elif command == "focus_near":
                cmd_code = 0x20
                combine_code2 = 0
            elif command == "focus_far":
                cmd_code = 0x40
                combine_code2 = 0
            elif command == "focus_stop":
                cmd_code = 0x00
            # GB4 PTZ扩展命令 — 光圈控制
            elif command == "iris_open":
                cmd_code = 0x80
                combine_code2 = 0
            elif command == "iris_close":
                cmd_code = 0x01
                combine_code2 = 0
            elif command == "iris_stop":
                cmd_code = 0x00

            ptz_hex = self._get_ptz_cmd(cmd_code, param1, param2, combine_code2)

            # GB4 PTZ扩展命令 — 预置位/巡航/扫描/雨刷/辅助/录像/布防/复位
            # These commands use specialized PTZ hex formats, not the standard direction/zoom format
            _preset_id = int((drag_data or {}).get("preset_id", 0)) if drag_data else 0
            _cruise_id = int((drag_data or {}).get("cruise_id", 0)) if drag_data else 0
            _scan_id = int((drag_data or {}).get("scan_id", 0)) if drag_data else 0
            _aux_id = int((drag_data or {}).get("aux_id", 2)) if drag_data else 2

            if command == "preset_set":
                ptz_hex = self._get_preset_set_cmd(max(1, _preset_id))
            elif command == "preset_goto":
                ptz_hex = self._get_preset_cmd(max(1, _preset_id))
            elif command == "preset_clear":
                ptz_hex = self._get_preset_delete_cmd(max(1, _preset_id))
            elif command == "cruise_start":
                ptz_hex = self._get_cruise_cmd(max(1, _cruise_id), 1, 'start')
            elif command == "cruise_stop":
                ptz_hex = self._get_cruise_cmd(max(1, _cruise_id), 1, 'stop')
            elif command == "cruise_add_preset":
                ptz_hex = self._get_cruise_cmd(max(1, _cruise_id), max(1, _preset_id), 'add')
            elif command == "cruise_del_preset":
                ptz_hex = self._get_cruise_cmd(max(1, _cruise_id), max(1, _preset_id), 'delete')
            elif command == "cruise_set_speed":
                ptz_hex = self._get_cruise_cmd(max(1, _cruise_id), 1, 'set_speed', speed=speed)
            elif command == "cruise_set_time":
                _stay_time = int((drag_data or {}).get("stay_time", 5)) if drag_data else 5
                ptz_hex = self._get_cruise_cmd(max(1, _cruise_id), 1, 'set_time', stay_time=_stay_time)
            elif command == "scan_start":
                ptz_hex = self._get_scan_cmd(max(0, _scan_id), 'start')
            elif command == "scan_stop":
                ptz_hex = self._get_scan_cmd(max(0, _scan_id), 'stop')
            elif command == "scan_set_speed":
                ptz_hex = self._get_scan_cmd(max(0, _scan_id), 'set_speed', speed=speed)
            elif command == "scan_set_left_limit":
                ptz_hex = self._get_scan_cmd(max(0, _scan_id), 'set_left')
            elif command == "scan_set_right_limit":
                ptz_hex = self._get_scan_cmd(max(0, _scan_id), 'set_right')
            elif command == "wiper_on":
                ptz_hex = self._get_wiper_cmd("on")
            elif command == "wiper_off":
                ptz_hex = self._get_wiper_cmd("off")
            elif command == "aux_on":
                ptz_hex = self._get_aux_switch_cmd(_aux_id, "on")
            elif command == "aux_off":
                ptz_hex = self._get_aux_switch_cmd(_aux_id, "off")
            # GB4 PTZ扩展命令 — 录像/布防/复位（委托device_control模块）
            elif command in ("record_start", "record_stop", "guard_on", "guard_off", "reset_alarm"):
                # These commands use DeviceControl XML (not PTZCmd), delegate to device_control
                from app.sip.device_control import device_control
                if device_control:
                    _transport_info = ((asset.ip_addr, asset.port), asset.transport, transport)
                    if command == "record_start":
                        await device_control.send_record_control(asset, channel_id, _transport_info, "Record")
                    elif command == "record_stop":
                        await device_control.send_record_control(asset, channel_id, _transport_info, "StopRecord")
                    elif command == "guard_on":
                        await device_control.send_guard(asset, channel_id, _transport_info, "SetGuard")
                    elif command == "guard_off":
                        await device_control.send_guard(asset, channel_id, _transport_info, "ResetGuard")
                    elif command == "reset_alarm":
                        await device_control.send_alarm_reset(asset, channel_id, _transport_info)
                logger.info(f"[trace_id=] Sent PTZ {command} to {channel_id} via device_control")
                return
            
            xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<PTZCmd>{ptz_hex}</PTZCmd>
<Info><ControlPriority>5</ControlPriority></Info>
</Control>
"""  # 添加ControlPriority字段，与commander.py一致，GB28181标准推荐
        # Create Request
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch=z9hG4bK{sn}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={sn}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_ptz@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        
        req.body = xml_body
        
        # Send
        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)
        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent PTZ {command} to {channel_id}")
        _sip_trace_log(
            "device_ptz_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            command=command,
            speed=speed,
            proto=proto,
            addr=str(addr),
        )

    def _get_preset_cmd(self, preset_id: int) -> str:
        """."""
        preset_id = max(1, min(255, int(preset_id)))
        cmd = [0xA5, 0x0F, 0x01, 0x82, 0x00, preset_id, 0x00]
        checksum = sum(cmd) % 256
        cmd.append(checksum)
        return "".join([f"{b:02X}" for b in cmd])

    def _get_preset_set_cmd(self, preset_id: int) -> str:
        """GB preset set: A5 0F 01 81 00 [preset_id] 00 + checksum. preset_id 1-255."""
        preset_id = max(1, min(255, int(preset_id)))
        cmd = [0xA5, 0x0F, 0x01, 0x81, 0x00, preset_id, 0x00]
        checksum = sum(cmd) % 256
        cmd.append(checksum)
        return "".join([f"{b:02X}" for b in cmd])

    def _get_preset_delete_cmd(self, preset_id: int) -> str:
        """."""
        preset_id = max(1, min(255, int(preset_id)))
        cmd = [0xA5, 0x0F, 0x01, 0x83, 0x00, preset_id, 0x00]
        checksum = sum(cmd) % 256
        cmd.append(checksum)
        return "".join([f"{b:02X}" for b in cmd])

    async def send_preset(self, asset, resource, transport_info: tuple, preset_id: int):
        """."""
        addr, proto, transport = transport_info
        channel_id = resource.gb_id
        _ptz_rate_limiter.cancel_pending(asset.gb_id)  # PTZ最新指令优先策略 — 新指令取消旧指令
        if not await _ptz_rate_limiter.acquire(asset.gb_id):  # PTZ最新指令优先策略 — 被新指令取代则跳过
            return
        ptz_hex = self._get_preset_cmd(preset_id)
        sn = _next_sn()  # SN序列号使用递增计数器替代hash
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<PTZCmd>{ptz_hex}</PTZCmd>
<Info><ControlPriority>5</ControlPriority></Info>
</Control>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{asset.gb_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch=z9hG4bK{sn}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={sn}"
        req.headers["To"] = f"<sip:{asset.gb_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_preset@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        req.body = xml_body
        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)
        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent PTZ preset {preset_id} to {channel_id}")
        _sip_trace_log(
            "device_ptz_preset_sent",
            trace_id=trace_id,
            device_id=asset.gb_id,
            channel_id=channel_id,
            preset_id=preset_id,
            proto=proto,
            addr=str(addr),
        )

    async def send_preset_set(self, asset, resource, transport_info: tuple, preset_id: int):
        """."""
        addr, proto, transport = transport_info
        channel_id = resource.gb_id
        _ptz_rate_limiter.cancel_pending(asset.gb_id)  # PTZ最新指令优先策略 — 新指令取消旧指令
        if not await _ptz_rate_limiter.acquire(asset.gb_id):  # PTZ最新指令优先策略 — 被新指令取代则跳过
            return
        ptz_hex = self._get_preset_set_cmd(preset_id)
        sn = _next_sn()  # SN序列号使用递增计数器替代hash
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<PTZCmd>{ptz_hex}</PTZCmd>
<Info><ControlPriority>5</ControlPriority></Info>
</Control>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{asset.gb_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch=z9hG4bK{sn}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={sn}"
        req.headers["To"] = f"<sip:{asset.gb_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_preset_set@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        req.body = xml_body
        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)
        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent PTZ preset set {preset_id} to {channel_id}")
        _sip_trace_log(
            "device_ptz_preset_set_sent",
            trace_id=trace_id,
            device_id=asset.gb_id,
            channel_id=channel_id,
            preset_id=preset_id,
            proto=proto,
            addr=str(addr),
        )

    async def send_preset_delete(self, asset, resource, transport_info: tuple, preset_id: int):
        """."""
        addr, proto, transport = transport_info
        channel_id = resource.gb_id
        _ptz_rate_limiter.cancel_pending(asset.gb_id)  # PTZ最新指令优先策略 — 新指令取消旧指令
        if not await _ptz_rate_limiter.acquire(asset.gb_id):  # PTZ最新指令优先策略 — 被新指令取代则跳过
            return
        ptz_hex = self._get_preset_delete_cmd(preset_id)
        sn = _next_sn()  # SN序列号使用递增计数器替代hash
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<PTZCmd>{ptz_hex}</PTZCmd>
<Info><ControlPriority>5</ControlPriority></Info>
</Control>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{asset.gb_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch=z9hG4bK{sn}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={sn}"
        req.headers["To"] = f"<sip:{asset.gb_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_preset_delete@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        req.body = xml_body
        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)
        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent PTZ preset delete {preset_id} to {channel_id}")
        _sip_trace_log(
            "device_ptz_preset_delete_sent",
            trace_id=trace_id,
            device_id=asset.gb_id,
            channel_id=channel_id,
            preset_id=preset_id,
            proto=proto,
            addr=str(addr),
        )

    # ==================== 光圈控制 ====================
    
    def _get_iris_cmd(self, command: str, speed: int = 128) -> str:
        """
        生成光圈控制命令
        command: 'in'(光圈?, 'out'(光圈?, 'stop'
        speed: 0-255
        """
        speed = max(0, min(255, int(speed)))
        
        if command == 'in':
            # 光圈控制指令扩展为8字节
            cmd = [0xA5, 0x0F, 0x01, 0x02, speed, 0x00, 0x00]
        elif command == 'out':
            cmd = [0xA5, 0x0F, 0x01, 0x04, speed, 0x00, 0x00]
        else:  # stop
            cmd = [0xA5, 0x0F, 0x01, 0x00, 0x00, 0x00, 0x00]
        
        checksum = sum(cmd) % 256
        cmd.append(checksum)
        return "".join([f"{b:02X}" for b in cmd])
    
    async def send_iris(self, asset, resource, transport_info: tuple, command: str, speed: int = 128):
        """."""
        addr, proto, transport = transport_info
        channel_id = resource.gb_id
        _ptz_rate_limiter.cancel_pending(asset.gb_id)  # PTZ最新指令优先策略 — 新指令取消旧指令
        if not await _ptz_rate_limiter.acquire(asset.gb_id):  # PTZ最新指令优先策略 — 被新指令取代则跳过
            return
        ptz_hex = self._get_iris_cmd(command, speed)
        sn = _next_sn()  # SN序列号使用递增计数器替代hash
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<PTZCmd>{ptz_hex}</PTZCmd>
<Info><ControlPriority>5</ControlPriority></Info>
</Control>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{asset.gb_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch=z9hG4bK{sn}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={sn}"
        req.headers["To"] = f"<sip:{asset.gb_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_iris@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        req.body = xml_body
        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)
        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent IRIS {command} to {channel_id}")
        _sip_trace_log(
            "device_iris_sent",
            trace_id=trace_id,
            device_id=asset.gb_id,
            channel_id=channel_id,
            command=command,
            speed=speed,
            proto=proto,
            addr=str(addr),
        )

    # ==================== 聚焦控制 ====================
    
    def _get_focus_cmd(self, command: str, speed: int = 128) -> str:
        """
        生成聚焦控制命令
        command: 'near'(近焦), 'far'(远焦), 'stop'
        speed: 0-255
        """
        speed = max(0, min(255, int(speed)))
        
        if command == 'near':
            # 聚焦控制指令扩展为8字节
            cmd = [0xA5, 0x0F, 0x01, 0x01, speed, 0x00, 0x00]
        elif command == 'far':
            cmd = [0xA5, 0x0F, 0x01, 0x03, speed, 0x00, 0x00]
        else:  # stop
            cmd = [0xA5, 0x0F, 0x01, 0x00, 0x00, 0x00, 0x00]
        
        checksum = sum(cmd) % 256
        cmd.append(checksum)
        return "".join([f"{b:02X}" for b in cmd])
    
    async def send_focus(self, asset, resource, transport_info: tuple, command: str, speed: int = 128):
        """."""
        addr, proto, transport = transport_info
        channel_id = resource.gb_id
        _ptz_rate_limiter.cancel_pending(asset.gb_id)  # PTZ最新指令优先策略 — 新指令取消旧指令
        if not await _ptz_rate_limiter.acquire(asset.gb_id):  # PTZ最新指令优先策略 — 被新指令取代则跳过
            return
        ptz_hex = self._get_focus_cmd(command, speed)
        sn = _next_sn()  # SN序列号使用递增计数器替代hash
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<PTZCmd>{ptz_hex}</PTZCmd>
<Info><ControlPriority>5</ControlPriority></Info>
</Control>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{asset.gb_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch=z9hG4bK{sn}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={sn}"
        req.headers["To"] = f"<sip:{asset.gb_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_focus@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        req.body = xml_body
        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)
        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent FOCUS {command} to {channel_id}")
        _sip_trace_log(
            "device_focus_sent",
            trace_id=trace_id,
            device_id=asset.gb_id,
            channel_id=channel_id,
            command=command,
            speed=speed,
            proto=proto,
            addr=str(addr),
        )

    # ==================== 巡航控制 ====================
    
    def _get_cruise_cmd(self, cruise_id: int, preset_id: int, action: str, speed: int = 128, stay_time: int = 5) -> str:
        """
        生成巡航控制命令
        cruise_id: 巡航组号 1-255
        preset_id: 预置位号 1-255
        action: 'add'(添加), 'delete'(删除), 'set_speed'(设置速度), 'set_time'(设置停留时间),
                'start'(开始巡?, 'stop'(停止巡航), 'delete_group'(删除巡航?
        speed: 巡航速度 1-4095
        stay_time: 停留时间 1-4095 (?
        """
        cruise_id = max(1, min(255, int(cruise_id)))
        preset_id = max(1, min(255, int(preset_id)))
        
        if action == 'add':
            # 巡航添加指令扩展为8字节，GB28181标准PTZCmd固定8字节格式
            cmd = [0xA5, 0x0F, 0x01, 0x82, cruise_id, preset_id, 0x00]
        elif action == 'delete':
            # 巡航删除指令扩展为8字节
            cmd = [0xA5, 0x0F, 0x01, 0x83, cruise_id, preset_id, 0x00]
        elif action == 'set_speed':
            # 设置巡航速度: A5 0F 01 84 [cruise_id] [speed_h] [speed_l]
            speed = max(1, min(4095, int(speed)))
            speed_h = (speed >> 8) & 0xFF
            speed_l = speed & 0xFF
            cmd = [0xA5, 0x0F, 0x01, 0x84, cruise_id, speed_h, speed_l]
        elif action == 'set_time':
            # 设置停留时间: A5 0F 01 85 [cruise_id] [time_h] [time_l]
            stay_time = max(1, min(4095, int(stay_time)))
            time_h = (stay_time >> 8) & 0xFF
            time_l = stay_time & 0xFF
            cmd = [0xA5, 0x0F, 0x01, 0x85, cruise_id, time_h, time_l]
        elif action == 'start':
            # 开始巡航指令扩展为8字节
            cmd = [0xA5, 0x0F, 0x01, 0x86, cruise_id, 0x00, 0x00]
        elif action == 'stop':
            # 停止巡航指令扩展为8字节
            cmd = [0xA5, 0x0F, 0x01, 0x87, cruise_id, 0x00, 0x00]
        elif action == 'delete_group':
            # 删除巡航组指令扩展为8字节
            cmd = [0xA5, 0x0F, 0x01, 0x88, cruise_id, 0x00, 0x00]
        else:
            # fallback指令扩展为8字节
            cmd = [0xA5, 0x0F, 0x01, 0x00, 0x00, 0x00, 0x00]
        
        checksum = sum(cmd) % 256
        cmd.append(checksum)
        return "".join([f"{b:02X}" for b in cmd])
    
    async def send_cruise(self, asset, resource, transport_info: tuple, cruise_id: int, preset_id: int, action: str, speed: int = 128, stay_time: int = 5):
        """."""
        addr, proto, transport = transport_info
        channel_id = resource.gb_id
        _ptz_rate_limiter.cancel_pending(asset.gb_id)  # PTZ最新指令优先策略 — 新指令取消旧指令
        if not await _ptz_rate_limiter.acquire(asset.gb_id):  # PTZ最新指令优先策略 — 被新指令取代则跳过
            return
        ptz_hex = self._get_cruise_cmd(cruise_id, preset_id, action, speed, stay_time)
        sn = _next_sn()  # SN序列号使用递增计数器替代hash
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<PTZCmd>{ptz_hex}</PTZCmd>
<Info><ControlPriority>5</ControlPriority></Info>
</Control>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{asset.gb_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch=z9hG4bK{sn}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={sn}"
        req.headers["To"] = f"<sip:{asset.gb_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_cruise@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        req.body = xml_body
        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)
        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent CRUISE {action} to {channel_id}, cruise_id={cruise_id}")
        _sip_trace_log(
            "device_cruise_sent",
            trace_id=trace_id,
            device_id=asset.gb_id,
            channel_id=channel_id,
            cruise_id=cruise_id,
            action=action,
            proto=proto,
            addr=str(addr),
        )

    # ==================== 扫描控制 ====================
    
    def _get_scan_cmd(self, scan_id: int, action: str, speed: int = 128) -> str:
        """
        生成扫描控制命令
        scan_id: 扫描组号 0-255
        action: 'start'(开?, 'stop'(停止), 'set_left'(设置左边?, 'set_right'(设置右边?, 'set_speed'(设置速度)
        speed: 扫描速度 1-4095
        """
        scan_id = max(0, min(255, int(scan_id)))
        
        if action == 'start':
            # 扫描开始指令扩展为8字节
            cmd = [0xA5, 0x0F, 0x01, 0x99, scan_id, 0x00, 0x00]
        elif action == 'stop':
            # 扫描停止指令扩展为8字节
            cmd = [0xA5, 0x0F, 0x01, 0x9A, scan_id, 0x00, 0x00]
        elif action == 'set_left':
            # 设置左边界指令扩展为8字节
            cmd = [0xA5, 0x0F, 0x01, 0x9B, scan_id, 0x00, 0x00]
        elif action == 'set_right':
            # 设置右边界指令扩展为8字节
            cmd = [0xA5, 0x0F, 0x01, 0x9C, scan_id, 0x00, 0x00]
        elif action == 'set_speed':
            # 设置扫描速度: A5 0F 01 9D [scan_id] [speed_h] [speed_l]
            speed = max(1, min(4095, int(speed)))
            speed_h = (speed >> 8) & 0xFF
            speed_l = speed & 0xFF
            cmd = [0xA5, 0x0F, 0x01, 0x9D, scan_id, speed_h, speed_l]
        else:
            # fallback指令扩展为8字节
            cmd = [0xA5, 0x0F, 0x01, 0x00, 0x00, 0x00, 0x00]
        
        checksum = sum(cmd) % 256
        cmd.append(checksum)
        return "".join([f"{b:02X}" for b in cmd])
    
    async def send_scan(self, asset, resource, transport_info: tuple, scan_id: int, action: str, speed: int = 128):
        """."""
        addr, proto, transport = transport_info
        channel_id = resource.gb_id
        _ptz_rate_limiter.cancel_pending(asset.gb_id)  # PTZ最新指令优先策略 — 新指令取消旧指令
        if not await _ptz_rate_limiter.acquire(asset.gb_id):  # PTZ最新指令优先策略 — 被新指令取代则跳过
            return
        ptz_hex = self._get_scan_cmd(scan_id, action, speed)
        sn = _next_sn()  # SN序列号使用递增计数器替代hash
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<PTZCmd>{ptz_hex}</PTZCmd>
<Info><ControlPriority>5</ControlPriority></Info>
</Control>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{asset.gb_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch=z9hG4bK{sn}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={sn}"
        req.headers["To"] = f"<sip:{asset.gb_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_scan@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        req.body = xml_body
        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)
        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent SCAN {action} to {channel_id}, scan_id={scan_id}")
        _sip_trace_log(
            "device_scan_sent",
            trace_id=trace_id,
            device_id=asset.gb_id,
            channel_id=channel_id,
            scan_id=scan_id,
            action=action,
            proto=proto,
            addr=str(addr),
        )

    # ==================== 雨刷/辅助开关控制（设备兼容性相关） ====================

    def _get_wiper_cmd(self, command: str) -> str:
        """
        生成雨刷控制命令?
        说明：国标设备兼容性差异较大，此处采用常见私有扩展编码?
        """
        if command == "on":
            # 雨刷控制指令扩展为8字节
            cmd = [0xA5, 0x0F, 0x01, 0x30, 0x00, 0x01, 0x00]
        elif command == "off":
            cmd = [0xA5, 0x0F, 0x01, 0x30, 0x00, 0x00, 0x00]
        else:  # stop
            cmd = [0xA5, 0x0F, 0x01, 0x00, 0x00, 0x00, 0x00]
        checksum = sum(cmd) % 256
        cmd.append(checksum)
        return "".join([f"{b:02X}" for b in cmd])

    async def send_wiper(self, asset, resource, transport_info: tuple, command: str):
        channel_id = resource.gb_id
        _ptz_rate_limiter.cancel_pending(asset.gb_id)  # PTZ最新指令优先策略 — 新指令取消旧指令
        if not await _ptz_rate_limiter.acquire(asset.gb_id):  # PTZ最新指令优先策略 — 被新指令取代则跳过
            return
        ptz_hex = self._get_wiper_cmd(command)
        _wiper_sn = _next_sn()  # SN序列号使用递增计数器替代hash
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{_wiper_sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<PTZCmd>{ptz_hex}</PTZCmd>
<Info><ControlPriority>5</ControlPriority></Info>
</Control>
"""
        trace_id, proto, addr = await self._send_device_control_xml(
            asset, channel_id, transport_info, xml_body, "wiper", f"WIPER {command}"
        )
        _sip_trace_log(
            "device_wiper_sent",
            trace_id=trace_id,
            device_id=asset.gb_id,
            channel_id=channel_id,
            command=command,
            proto=proto,
            addr=str(addr),
        )

    def _get_aux_switch_cmd(self, aux_id: int, command: str) -> str:
        """
        生成辅助开关命令?
        说明：按常见扩展编码拼装，设备不支持时会忽略该指令?
        """
        aux_id = max(2, min(255, int(aux_id)))
        state = 0x01 if command == "on" else 0x00
        # 辅助开关指令扩展为8字节
        cmd = [0xA5, 0x0F, 0x01, 0x31, aux_id, state, 0x00]
        checksum = sum(cmd) % 256
        cmd.append(checksum)
        return "".join([f"{b:02X}" for b in cmd])

    async def send_aux_switch(self, asset, resource, transport_info: tuple, aux_id: int, command: str):
        channel_id = resource.gb_id
        _ptz_rate_limiter.cancel_pending(asset.gb_id)  # PTZ最新指令优先策略 — 新指令取消旧指令
        if not await _ptz_rate_limiter.acquire(asset.gb_id):  # PTZ最新指令优先策略 — 被新指令取代则跳过
            return
        ptz_hex = self._get_aux_switch_cmd(aux_id, command)
        _aux_sn = _next_sn()  # SN序列号使用递增计数器替代hash
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{_aux_sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<PTZCmd>{ptz_hex}</PTZCmd>
<Info><ControlPriority>5</ControlPriority></Info>
</Control>
"""
        trace_id, proto, addr = await self._send_device_control_xml(
            asset, channel_id, transport_info, xml_body, "aux", f"AUX {command} aux_id={aux_id}"
        )
        _sip_trace_log(
            "device_aux_switch_sent",
            trace_id=trace_id,
            device_id=asset.gb_id,
            channel_id=channel_id,
            aux_id=aux_id,
            command=command,
            proto=proto,
            addr=str(addr),
        )

# Singleton
sip_ptz = None


# R-12 添加get_sip_ptz()安全访问函数，防止启动前访问崩溃
def get_sip_ptz() -> "SipPtz | None":
    return sip_ptz
