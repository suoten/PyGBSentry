"""
GB28181 设备控制模块
支持：布?撤防、报警复位、远程重启、录像控制、强制关键帧?
"""
import itertools
from app.sip.message import SipMessage

# P0-fix: 移除 _SIP_SN_MIN/_SIP_SN_MAX 窄范围随机 SN，改用全局单调递增计数器
# 与 commander.py 共享相同的递增策略，避免 CSeq/SN 回退导致设备拒绝命令
_cseq_counter = itertools.count(1)
_sn_counter = itertools.count(10001)


def _next_cseq() -> int:
    return next(_cseq_counter)


def _next_sn() -> int:
    return next(_sn_counter)


# GB28181 互操作性：UAC 应在请求中声明支持的方法集
_SIP_ALLOW_HEADER = "INVITE, ACK, CANCEL, BYE, OPTIONS, INFO, SUBSCRIBE, NOTIFY, MESSAGE, UPDATE"

from xml.sax.saxutils import escape as _xml_escape
from app.core.config import settings, sip_host_for_contact, sip_via_host, sip_from_to_host
# 统一使用 sip_trace 模块的 trace 函数，消除重复定义
from app.sip.sip_trace import sip_trace_should_log as _sip_trace_should_log, sip_trace_log as _sip_trace_log
from app.sip.send import send_sip_bytes
from loguru import logger
import secrets  # P4 安全随机数 — random→secrets
import string


def _attach_trace_header(req: SipMessage) -> str:
    """返回 Call-ID 作为 trace_id 用于日志关联。

    FIX: [2026-07-21 P0] 不再向 SIP 请求添加 X-Trace-ID 头域。
    实测发现 EasyGBS 等非标准 SIP 客户端对非标准头域（X- 开头）敏感，会返回 400 Bad Request。
    """
    return (req.get_header("Call-ID") or "").strip()


def _attach_common_headers(req: SipMessage, device_id: str) -> None:
    """为 out-of-dialog SIP 请求补全 Contact 和 Allow 头（RFC 3261 §20.5/§20.10）。

    FIX: [2026-07-21 P0] 兼容非标准 SIP 客户端（如 EasyGBS 级联平台）：
    实测发现 EasyGBS 对 MESSAGE 请求中的 Contact/Allow 头域敏感，会返回 400 Bad Request。
    RFC 3261 §20.10 仅强制 INVITE 必须带 Contact，MESSAGE/OPTIONS/INFO 等方法不要求。
    此处对 MESSAGE 请求完全跳过 Contact/Allow 头的补全，与 commander.py 行为一致。
    """
    _method = (getattr(req, "method", "") or "").strip().upper()
    if _method == "MESSAGE":
        return
    if not req.get_header("Contact"):
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
    if not req.get_header("Allow"):
        req.headers["Allow"] = _SIP_ALLOW_HEADER


class DeviceControl:
    """."""

    def __init__(self, sip_server):
        self.sip_server = sip_server

    async def send_guard(self, asset, channel_id: str, transport_info: tuple, guard_cmd: str):
        """
        发送布?撤防命令
        
        Args:
            asset: 设备资产对象
            channel_id: 通道ID
            transport_info: (addr, proto, transport) 传输信息
            guard_cmd: "SetGuard" ?"ResetGuard"
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id
        
        # Build XML body
        sn = _next_sn()  # P0-fix: 单调递增 SN，避免窄范围随机碰撞
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<GuardCmd>{_xml_escape(guard_cmd)}</GuardCmd>
<Info>
<ControlPriority>5</ControlPriority>
</Info>
</Control>
"""
        
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        
        branch = f"z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §8.1.1.7）
        tag = secrets.token_hex(8)  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §19.3）
        
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = f"{secrets.token_hex(8)}@{sip_via_host()}"  # FIX [2026-07-22 P1]: 去后缀+SIP_DOMAIN，兼容非标准客户端
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # P0-fix: 单调递增 CSeq，避免硬编码 1 被设备当作重传丢弃
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req, device_id)  # P1-fix: 补全 Contact + Allow 头
        
        req.body = xml_body
        
        # Send
        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)
        
        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent GUARD {guard_cmd} to {channel_id}")
        _sip_trace_log(
            "device_guard_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            guard_cmd=guard_cmd,
            proto=proto,
            addr=str(addr),
        )

    async def send_alarm_reset(self, asset, channel_id: str, transport_info: tuple, alarm_method: str = "", alarm_type: str = ""):
        """
        发送报警复位命?
        
        Args:
            asset: 设备资产对象
            channel_id: 通道ID
            transport_info: (addr, proto, transport) 传输信息
            alarm_method: 报警方式
            alarm_type: 报警类型
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id
        
        sn = _next_sn()  # P0-fix: 单调递增 SN，避免窄范围随机碰撞
        # P1-fix: GB/T 28181-2022 §A.2.4 规定 DeviceControl 命令应包含 <Info><ControlPriority> 节点
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<AlarmCmd>ResetAlarm</AlarmCmd>
<AlarmMethod>{_xml_escape(alarm_method)}</AlarmMethod>
<AlarmType>{_xml_escape(alarm_type)}</AlarmType>
<Info>
<ControlPriority>5</ControlPriority>
</Info>
</Control>
"""
        
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        
        branch = f"z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §8.1.1.7）
        tag = secrets.token_hex(8)  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §19.3）
        
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = f"{secrets.token_hex(8)}@{sip_via_host()}"
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # P0-fix: 单调递增 CSeq，避免硬编码 1 被设备当作重传丢弃
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req, device_id)  # P1-fix: 补全 Contact + Allow 头
        
        req.body = xml_body
        
        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)
        
        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent ALARM RESET to {channel_id}")
        _sip_trace_log(
            "device_alarm_reset_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            proto=proto,
            addr=str(addr),
        )

    async def send_teleboot(self, asset, transport_info: tuple):
        """
        发送远程重启命?
        
        Args:
            asset: 设备资产对象
            transport_info: (addr, proto, transport) 传输信息
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id
        
        sn = _next_sn()  # P0-fix: 单调递增 SN，避免窄范围随机碰撞
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(device_id)}</DeviceID>
<TeleBoot>Boot</TeleBoot>
</Control>
"""
        
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        
        branch = f"z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §8.1.1.7）
        tag = secrets.token_hex(8)  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §19.3）
        
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = f"{secrets.token_hex(8)}@{sip_via_host()}"
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # P0-fix: 单调递增 CSeq，避免硬编码 1 被设备当作重传丢弃
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req, device_id)  # P1-fix: 补全 Contact + Allow 头
        
        req.body = xml_body
        
        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)
        
        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent TELEBOOT to {device_id}")
        _sip_trace_log(
            "device_teleboot_sent",
            trace_id=trace_id,
            device_id=device_id,
            proto=proto,
            addr=str(addr),
        )

    async def send_record_control(self, asset, channel_id: str, transport_info: tuple, record_cmd: str):
        """
        发送录像控制命?
        
        Args:
            asset: 设备资产对象
            channel_id: 通道ID
            transport_info: (addr, proto, transport) 传输信息
            record_cmd: "Record" ?"StopRecord"
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id
        
        sn = _next_sn()  # P0-fix: 单调递增 SN，避免窄范围随机碰撞
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<RecordCmd>{_xml_escape(record_cmd)}</RecordCmd>
<Info>
<ControlPriority>5</ControlPriority>
</Info>
</Control>
"""
        
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        
        branch = f"z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §8.1.1.7）
        tag = secrets.token_hex(8)  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §19.3）
        
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = f"{secrets.token_hex(8)}@{sip_via_host()}"
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # P0-fix: 单调递增 CSeq，避免硬编码 1 被设备当作重传丢弃
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req, device_id)  # P1-fix: 补全 Contact + Allow 头
        
        req.body = xml_body
        
        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)
        
        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent RECORD {record_cmd} to {channel_id}")
        _sip_trace_log(
            "device_record_control_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            record_cmd=record_cmd,
            proto=proto,
            addr=str(addr),
        )

    async def send_iframe_request(self, asset, channel_id: str, transport_info: tuple):
        """
        发送强制关键帧命令
        
        Args:
            asset: 设备资产对象
            channel_id: 通道ID
            transport_info: (addr, proto, transport) 传输信息
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id
        
        sn = _next_sn()  # P0-fix: 单调递增 SN，避免窄范围随机碰撞
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<IFrameCmd>Send</IFrameCmd>
<Info>
<ControlPriority>5</ControlPriority>
</Info>
</Control>
"""
        
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        
        branch = f"z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §8.1.1.7）
        tag = secrets.token_hex(8)  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §19.3）
        
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = f"{secrets.token_hex(8)}@{sip_via_host()}"
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # P0-fix: 单调递增 CSeq，避免硬编码 1 被设备当作重传丢弃
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req, device_id)  # P1-fix: 补全 Contact + Allow 头
        
        req.body = xml_body
        
        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)
        
        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent IFRAME REQUEST to {channel_id}")
        _sip_trace_log(
            "device_iframe_request_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            proto=proto,
            addr=str(addr),
        )


    async def send_config_download(
        self,
        device_id: str,
        channel_id: str,
        transport_info: tuple,
        config_type: str = "BasicParam",
    ) -> str:
        """发送配置下载查询 (CmdType=ConfigDownload)"""
        # 实现 GB28181-2022 ConfigDownload 配置下载查询
        addr, proto, transport = transport_info

        sn = _next_sn()  # P0-fix: 单调递增 SN，避免窄范围随机碰撞
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>ConfigDownload</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id or device_id)}</DeviceID>
<ConfigType>{_xml_escape(config_type)}</ConfigType>
</Query>
"""

        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §8.1.1.7）
        tag = secrets.token_hex(8)  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §19.3）

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = f"{secrets.token_hex(8)}@{sip_via_host()}"
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # P0-fix: 单调递增 CSeq，避免硬编码 1 被设备当作重传丢弃
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req, device_id)  # P1-fix: 补全 Contact + Allow 头

        req.body = xml_body

        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)

        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent ConfigDownload to {channel_id or device_id}, config_type={config_type}")
        _sip_trace_log(
            "device_config_download_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            config_type=config_type,
            proto=proto,
            addr=str(addr),
        )
        return str(sn)

    # GB14 设备状态查询 — GB28181设备状态查询
    async def send_device_status_query(self, asset, transport_info: tuple) -> bool:
        """Send device status query (Query/DeviceStatus) per GB28181"""
        addr, proto, transport = transport_info
        device_id = asset.gb_id

        sn = _next_sn()  # P0-fix: 单调递增 SN，避免窄范围随机碰撞
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>DeviceStatus</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(device_id)}</DeviceID>
</Query>
"""

        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-17 P1]: 64位随机性
        tag = secrets.token_hex(8)  # FIX [2026-07-17 P1]: 64位随机性

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = f"{secrets.token_hex(8)}@{sip_via_host()}"
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # P0-fix: 单调递增 CSeq，避免硬编码 1 被设备当作重传丢弃
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req, device_id)  # P1-fix: 补全 Contact + Allow 头

        req.body = xml_body

        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)

        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent DeviceStatus query to {device_id}")
        _sip_trace_log(
            "device_status_query_sent",
            trace_id=trace_id,
            device_id=device_id,
            proto=proto,
            addr=str(addr),
        )
        return True

    # 预置位查询 — GB28181 PresetQuery，与wvp对齐
    async def send_preset_query(
        self,
        device_id: str,
        channel_id: str,
        transport_info: tuple,
    ) -> str:
        """Send preset position query (Query/PresetQuery) per GB28181"""
        addr, proto, transport = transport_info

        sn = _next_sn()  # P0-fix: 单调递增 SN，避免窄范围随机碰撞
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>PresetQuery</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id or device_id)}</DeviceID>
</Query>
"""

        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-17 P1]: 64位随机性
        tag = secrets.token_hex(8)  # FIX [2026-07-17 P1]: 64位随机性

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = f"{secrets.token_hex(8)}@{sip_via_host()}"
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # P0-fix: 单调递增 CSeq，避免硬编码 1 被设备当作重传丢弃
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req, device_id)  # P1-fix: 补全 Contact + Allow 头

        req.body = xml_body

        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)

        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent PresetQuery to {channel_id or device_id}")
        _sip_trace_log(
            "device_preset_query_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            proto=proto,
            addr=str(addr),
        )
        return str(sn)

    async def send_config_upload(
        self,
        device_id: str,
        channel_id: str,
        transport_info: tuple,
        config_type: str = "BasicParam",
        config_data: str = "",
    ) -> str:
        """发送设备配置设置/下发 (CmdType=ConfigUpload)"""
        # 实现ConfigUpload设备配置设置/下发
        addr, proto, transport = transport_info

        sn = _next_sn()  # P0-fix: 单调递增 SN，避免窄范围随机碰撞
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>ConfigUpload</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id or device_id)}</DeviceID>
<ConfigType>{_xml_escape(config_type)}</ConfigType>
<ConfigData>{_xml_escape(config_data)}</ConfigData>
</Control>
"""

        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §8.1.1.7）
        tag = secrets.token_hex(8)  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §19.3）

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = f"{secrets.token_hex(8)}@{sip_via_host()}"
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # P0-fix: 单调递增 CSeq，避免硬编码 1 被设备当作重传丢弃
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req, device_id)  # P1-fix: 补全 Contact + Allow 头

        req.body = xml_body

        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)

        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent ConfigUpload to {channel_id or device_id}, config_type={config_type}")
        _sip_trace_log(
            "device_config_upload_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            config_type=config_type,
            proto=proto,
            addr=str(addr),
        )
        return str(sn)

    async def send_config_set(
        self,
        device_id: str,
        channel_id: str,
        transport_info: tuple,
        config_type: str = "BasicParam",
        config_params: dict = None,
    ) -> str:
        """发送配置设置命令 (CmdType=ConfigSet)"""
        # 实现 GB28181-2022 ConfigSet 配置设置
        addr, proto, transport = transport_info

        sn = _next_sn()  # P0-fix: 单调递增 SN，避免窄范围随机碰撞
        # 根据 config_type 构建 XML
        config_xml = ""
        if config_params:
            for key, value in config_params.items():
                config_xml += f"<{key}>{_xml_escape(str(value))}</{key}>\n"
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>ConfigSet</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id or device_id)}</DeviceID>
<ConfigType>{_xml_escape(config_type)}</ConfigType>
{config_xml}</Control>
"""

        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §8.1.1.7）
        tag = secrets.token_hex(8)  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §19.3）

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = f"{secrets.token_hex(8)}@{sip_via_host()}"
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # P0-fix: 单调递增 CSeq，避免硬编码 1 被设备当作重传丢弃
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req, device_id)  # P1-fix: 补全 Contact + Allow 头

        req.body = xml_body

        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)

        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent ConfigSet to {channel_id or device_id}, config_type={config_type}")
        _sip_trace_log(
            "device_config_set_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            config_type=config_type,
            proto=proto,
            addr=str(addr),
        )
        return str(sn)

    async def send_drag_zoom(
        self,
        asset,
        channel_id: str,
        transport_info: tuple,
        zoom_cmd: str,
        left_top_x: int,
        left_top_y: int,
        right_bottom_x: int,
        right_bottom_y: int,
    ):
        """发送框选缩放命令 (DragZoomIn/DragZoomOut)

        Args:
            asset: 设备资产对象
            channel_id: 通道ID
            transport_info: (addr, proto, transport) 传输信息
            zoom_cmd: "DragZoomIn" 或 "DragZoomOut"
            left_top_x: 框选左上角X坐标
            left_top_y: 框选左上角Y坐标
            right_bottom_x: 框选右下角X坐标
            right_bottom_y: 框选右下角Y坐标
        """
        # GB28181 DragZoom框选缩放 — 支持DragZoomIn/DragZoomOut设备控制命令
        addr, proto, transport = transport_info
        device_id = asset.gb_id

        if zoom_cmd not in ("DragZoomIn", "DragZoomOut"):
            raise ValueError(f"zoom_cmd must be DragZoomIn or DragZoomOut, got {zoom_cmd}")

        sn = _next_sn()  # P0-fix: 单调递增 SN，避免窄范围随机碰撞
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<{zoom_cmd}>
<Length>2</Length>
<Cmd>{zoom_cmd}</Cmd>
<PointList>
<Point><X>{int(left_top_x)}</X><Y>{int(left_top_y)}</Y></Point>
<Point><X>{int(right_bottom_x)}</X><Y>{int(right_bottom_y)}</Y></Point>
</PointList>
</{zoom_cmd}>
</Control>
"""

        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-17 P1]: 64位随机性
        tag = secrets.token_hex(8)  # FIX [2026-07-17 P1]: 64位随机性

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = f"{secrets.token_hex(8)}@{sip_via_host()}"
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # P0-fix: 单调递增 CSeq，避免硬编码 1 被设备当作重传丢弃
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req, device_id)  # P1-fix: 补全 Contact + Allow 头

        req.body = xml_body

        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)

        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent {zoom_cmd} to {channel_id}, rect=({left_top_x},{left_top_y})-({right_bottom_x},{right_bottom_y})")
        _sip_trace_log(
            "device_drag_zoom_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            zoom_cmd=zoom_cmd,
            left_top_x=left_top_x,
            left_top_y=left_top_y,
            right_bottom_x=right_bottom_x,
            right_bottom_y=right_bottom_y,
            proto=proto,
            addr=str(addr),
        )

    async def send_home_position(
        self,
        asset,
        channel_id: str,
        transport_info: tuple,
        enabled: bool = True,
        preset_index: int = 1,
        reset_time: int = 5,
    ):
        """发送看守位控制命令 (HomePosition)

        Args:
            asset: 设备资产对象
            channel_id: 通道ID
            transport_info: (addr, proto, transport) 传输信息
            enabled: 是否启用看守位
            preset_index: 预置位编号 (1-255)
            reset_time: 看守位回归时间(秒)
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id

        sn = _next_sn()  # P0-fix: 单调递增 SN，避免窄范围随机碰撞
        enabled_str = "Enable" if enabled else "Disable"
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<HomePosition>
<Enabled>{enabled_str}</Enabled>
<PresetIndex>{preset_index}</PresetIndex>
<ResetTime>{reset_time}</ResetTime>
</HomePosition>
</Control>
"""

        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-17 P1]: 64位随机性
        tag = secrets.token_hex(8)  # FIX [2026-07-17 P1]: 64位随机性

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = f"{secrets.token_hex(8)}@{sip_via_host()}"
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # P0-fix: 单调递增 CSeq，避免硬编码 1 被设备当作重传丢弃
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req, device_id)  # P1-fix: 补全 Contact + Allow 头

        req.body = xml_body

        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)

        trace_id = req.headers.get("Call-ID", "")
        logger.info(f"[trace_id={trace_id}] Sent HomePosition to {channel_id}, enabled={enabled}, preset={preset_index}")
        _sip_trace_log(
            "device_home_position_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            enabled=enabled,
            preset_index=preset_index,
            reset_time=reset_time,
            proto=proto,
            addr=str(addr),
        )


# Singleton instance
device_control = None
