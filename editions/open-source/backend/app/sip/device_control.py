"""
GB28181 设备控制模块
支持：布?撤防、报警复位、远程重启、录像控制、强制关键帧?
"""
from app.sip.message import SipMessage

_SIP_SN_MIN = 1000  # FIXED: 魔法数字提取为常量
_SIP_SN_MAX = 9999  # FIXED: 魔法数字提取为常量
from xml.sax.saxutils import escape as _xml_escape
from app.core.config import settings, sip_host_for_contact
# FIXED: 统一使用 sip_trace 模块的 trace 函数，消除重复定义
from app.sip.sip_trace import sip_trace_should_log as _sip_trace_should_log, sip_trace_log as _sip_trace_log
from app.sip.send import send_sip_bytes
import logging
import secrets  # FIXED: P4 安全随机数 — random→secrets
import string

logger = logging.getLogger(__name__)


def _attach_trace_header(req: SipMessage) -> None:
    call_id = (req.get_header("Call-ID") or "").strip()
    if call_id:
        req.headers["X-Trace-ID"] = call_id


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
        sn = secrets.randbelow(_SIP_SN_MAX - _SIP_SN_MIN + 1) + _SIP_SN_MIN  # FIXED: P4 安全随机数 — random→secrets
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<GuardCmd>{_xml_escape(guard_cmd)}</GuardCmd>
</Control>
"""
        
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        
        branch = f"z9hG4bK{secrets.token_hex(5)}"  # FIXED: P4 安全随机数 — random→secrets
        tag = secrets.token_hex(4)  # FIXED: P4 安全随机数 — random→secrets
        
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_guard@{sip_host_for_contact()}"
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
        
        sn = secrets.randbelow(_SIP_SN_MAX - _SIP_SN_MIN + 1) + _SIP_SN_MIN  # FIXED: P4 安全随机数 — random→secrets
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<AlarmCmd>ResetAlarm</AlarmCmd>
<AlarmMethod>{_xml_escape(alarm_method)}</AlarmMethod>
<AlarmType>{_xml_escape(alarm_type)}</AlarmType>
</Control>
"""
        
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        
        branch = f"z9hG4bK{secrets.token_hex(5)}"  # FIXED: P4 安全随机数 — random→secrets
        tag = secrets.token_hex(4)  # FIXED: P4 安全随机数 — random→secrets
        
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_alarm_reset@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        
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
        
        sn = secrets.randbelow(_SIP_SN_MAX - _SIP_SN_MIN + 1) + _SIP_SN_MIN  # FIXED: P4 安全随机数 — random→secrets
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
        
        branch = f"z9hG4bK{secrets.token_hex(5)}"  # FIXED: P4 安全随机数 — random→secrets
        tag = secrets.token_hex(4)  # FIXED: P4 安全随机数 — random→secrets
        
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_teleboot@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        
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
        
        sn = secrets.randbelow(_SIP_SN_MAX - _SIP_SN_MIN + 1) + _SIP_SN_MIN  # FIXED: P4 安全随机数 — random→secrets
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<RecordCmd>{_xml_escape(record_cmd)}</RecordCmd>
</Control>
"""
        
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        
        branch = f"z9hG4bK{secrets.token_hex(5)}"  # FIXED: P4 安全随机数 — random→secrets
        tag = secrets.token_hex(4)  # FIXED: P4 安全随机数 — random→secrets
        
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_record@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        
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
        
        sn = secrets.randbelow(_SIP_SN_MAX - _SIP_SN_MIN + 1) + _SIP_SN_MIN  # FIXED: P4 安全随机数 — random→secrets
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<IFrameCmd>Send</IFrameCmd>
</Control>
"""
        
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        
        branch = f"z9hG4bK{secrets.token_hex(5)}"  # FIXED: P4 安全随机数 — random→secrets
        tag = secrets.token_hex(4)  # FIXED: P4 安全随机数 — random→secrets
        
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_iframe@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        
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
        # FIXED: 实现 GB28181-2022 ConfigDownload 配置下载查询
        addr, proto, transport = transport_info

        sn = secrets.randbelow(_SIP_SN_MAX - _SIP_SN_MIN + 1) + _SIP_SN_MIN  # FIXED: P4 安全随机数 — random→secrets
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

        branch = f"z9hG4bK{secrets.token_hex(5)}"  # FIXED: P4 安全随机数 — random→secrets
        tag = secrets.token_hex(4)  # FIXED: P4 安全随机数 — random→secrets

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_config_dl@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)

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

    # FIXED: GB14 设备状态查询 — GB28181设备状态查询
    async def send_device_status_query(self, asset, transport_info: tuple) -> bool:
        """Send device status query (Query/DeviceStatus) per GB28181"""
        addr, proto, transport = transport_info
        device_id = asset.gb_id

        sn = secrets.randbelow(_SIP_SN_MAX - _SIP_SN_MIN + 1) + _SIP_SN_MIN
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

        branch = f"z9hG4bK{secrets.token_hex(5)}"
        tag = secrets.token_hex(4)

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_devstatus@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)

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

    # FIXED-P4: 预置位查询 — GB28181 PresetQuery，与wvp对齐
    async def send_preset_query(
        self,
        device_id: str,
        channel_id: str,
        transport_info: tuple,
    ) -> str:
        """Send preset position query (Query/PresetQuery) per GB28181"""
        addr, proto, transport = transport_info

        sn = secrets.randbelow(_SIP_SN_MAX - _SIP_SN_MIN + 1) + _SIP_SN_MIN
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

        branch = f"z9hG4bK{secrets.token_hex(5)}"
        tag = secrets.token_hex(4)

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_preset_q@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)

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
        # FIXED: 实现ConfigUpload设备配置设置/下发
        addr, proto, transport = transport_info

        sn = secrets.randbelow(_SIP_SN_MAX - _SIP_SN_MIN + 1) + _SIP_SN_MIN  # FIXED: P4 安全随机数 — random→secrets
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

        branch = f"z9hG4bK{secrets.token_hex(5)}"  # FIXED: P4 安全随机数 — random→secrets
        tag = secrets.token_hex(4)  # FIXED: P4 安全随机数 — random→secrets

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_config_ul@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)

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
        # FIXED: 实现 GB28181-2022 ConfigSet 配置设置
        addr, proto, transport = transport_info

        sn = secrets.randbelow(_SIP_SN_MAX - _SIP_SN_MIN + 1) + _SIP_SN_MIN  # FIXED: P4 安全随机数 — random→secrets
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

        branch = f"z9hG4bK{secrets.token_hex(5)}"  # FIXED: P4 安全随机数 — random→secrets
        tag = secrets.token_hex(4)  # FIXED: P4 安全随机数 — random→secrets

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_config_set@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)

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
        # FIXED: GB28181 DragZoom框选缩放 — 支持DragZoomIn/DragZoomOut设备控制命令
        addr, proto, transport = transport_info
        device_id = asset.gb_id

        if zoom_cmd not in ("DragZoomIn", "DragZoomOut"):
            raise ValueError(f"zoom_cmd must be DragZoomIn or DragZoomOut, got {zoom_cmd}")

        sn = secrets.randbelow(_SIP_SN_MAX - _SIP_SN_MIN + 1) + _SIP_SN_MIN
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

        branch = f"z9hG4bK{secrets.token_hex(5)}"
        tag = secrets.token_hex(4)

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_dragzoom@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)

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

        sn = secrets.randbelow(_SIP_SN_MAX - _SIP_SN_MIN + 1) + _SIP_SN_MIN
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

        branch = f"z9hG4bK{secrets.token_hex(5)}"
        tag = secrets.token_hex(4)

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}_homeposition@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"1 MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)

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
