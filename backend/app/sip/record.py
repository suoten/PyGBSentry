from app.sip.message import SipMessage
from xml.sax.saxutils import escape as _xml_escape
from app.sip.send import send_sip_bytes
from app.core.config import settings, sip_via_host, sip_from_to_host
from app.sip.sn import next_sn  # P2-2: 统一 SN 生成策略
from loguru import logger  # 统一使用 loguru 替代 logging
import datetime
import secrets  # P4 安全随机数 — random→secrets


class SipRecord:
    def __init__(self, sip_server):
        """Internal helper:   init  ."""
        self.sip_server = sip_server

    async def query_device_record(self, asset, resource, transport_info: tuple, start_time: datetime.datetime, end_time: datetime.datetime, page_size: int = 50, page_num: int = 1):  # datetime module vs datetime class, 录像查询分页支持
        """
        Send RecordInfo Query with pagination support.
        GB28181 规范支持 RecNum（每页条数）和 SumNum（总条数）分页参数。
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id
        channel_id = resource.gb_id

        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%S")
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%S")

        sn = next_sn()  # P2-2: 统一 SN 生成策略
        # 录像查询分页支持 — 添加RecNum/SumNum/PageNum分页参数，避免大量录像一次性返回
        # GB28181规范: page_num>1时添加SumNum=0(已知总数只需翻页)和PageNum; page_num==1时不添加PageNum(首次查询由设备返回SumNum)
        pagination_xml = f"<RecNum>{page_size}</RecNum>"
        if page_num > 1:
            pagination_xml += f"\n<SumNum>0</SumNum>\n<PageNum>{page_num}</PageNum>"
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>RecordInfo</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<StartTime>{start_str}</StartTime>
<EndTime>{end_str}</EndTime>
<Type>all</Type>
{pagination_xml}
</Query>
"""
        # Create Request
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch=z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-17 P1]: 64位随机性
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={secrets.token_hex(8)}"  # FIX [2026-07-17 P1]: 64位随机性
        req.headers["To"] = f"<sip:{device_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = f"{secrets.token_hex(8)}@{sip_via_host()}"  # FIX [2026-07-22 P1]: 去_rec后缀+SIP_DOMAIN，兼容非标准客户端
        req.headers["CSeq"] = f"{sn} MESSAGE"  # FIX [2026-07-17 P1-A3]: CSeq 单调递增 (RFC 3261 §22.2)
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME

        req.body = xml_body

        # Send
        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)

        logger.info(f"Sent RecordInfo Query to {channel_id}")
        return sn

    async def send_record_control(self, asset, resource, transport_info: tuple, action: str = "Record", stream_id: str = "") -> int:
        """
        录像控制命令 — 发送 Record/StopRecord 控制指令。
        GB28181 标准中 DeviceControl 的 RecordCmd 用于控制设备端录像。
        action: "Record" 或 "StopRecord"
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id
        channel_id = resource.gb_id

        sn = next_sn()  # P2-2: 统一 SN 生成策略
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<RecordCmd>{action}</RecordCmd>
</Control>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch=z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-21 P0]: 无后缀，兼容 EasyGBS 等非标准客户端
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={secrets.token_hex(8)}"  # FIX [2026-07-21 P0]: 无后缀，兼容 EasyGBS 等非标准客户端
        req.headers["To"] = f"<sip:{device_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = f"{secrets.token_hex(8)}@{sip_via_host()}"  # FIX [2026-07-22 P1]: 去_rc后缀+SIP_DOMAIN，兼容非标准客户端
        req.headers["CSeq"] = f"{sn} MESSAGE"  # FIX [2026-07-17 P1-A3]: CSeq 单调递增 (RFC 3261 §22.2)
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.body = xml_body

        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)
        logger.info(f"Sent RecordCmd ({action}) to {channel_id}")
        return sn

# Singleton
sip_record = None


def get_sip_record() -> "SipRecord":
    """Get the SipRecord singleton. Raises RuntimeError if not initialized."""
    global sip_record
    if sip_record is None:
        raise RuntimeError("SipRecord not initialized. Call init_sip_record() first.")
    return sip_record


def init_sip_record(sip_server) -> "SipRecord":
    """Initialize the SipRecord singleton. Called during SIP server startup."""
    global sip_record
    if sip_record is None:
        sip_record = SipRecord(sip_server)
    return sip_record
