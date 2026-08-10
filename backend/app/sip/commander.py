from app.sip.message import SipMessage
from xml.sax.saxutils import escape as _xml_escape
from app.core.config import settings, sip_host_for_contact, sip_via_host, sip_from_to_host
# 统一使用 sip_trace 模块的 trace 函数，消除重复定义
from app.sip.sip_trace import sip_trace_log as _sip_trace_log
from app.core.plugin_manager import plugin_manager, HOOK_ON_SIP_SEND
from app.sip.send import send_sip_bytes
from loguru import logger
import secrets
import itertools
from app.core.async_utils import fire_and_forget  # P0-16: 安全的火-忘任务

_cseq_counter = itertools.count(1)

def _next_cseq() -> int:
    return next(_cseq_counter)

# SN序列号使用递增计数器替代随机数
_sn_counter = itertools.count(10001)

def _next_sn() -> int:
    return next(_sn_counter)


# P1-fix [2026-07-17]: 统一封装 Via branch 和 Call-ID 生成器
# 原代码 branch=z9hG4bK{sn} 无随机性，进程重启后 SN 归零会导致 branch 重复，
# 违反 RFC 3261 §8.1.1.7（branch 必须全局唯一）。Call-ID 同理。
def _make_branch(prefix: str = "") -> str:
    """生成符合 RFC 3261 §8.1.1.7 的 Via branch 参数。

    z9hG4bK 前缀（magic cookie）+ 可选语义前缀 + 64 位密码学随机性。
    """
    rand = secrets.token_hex(8)  # 64 bits 随机性
    return f"z9hG4bK{prefix}{rand}" if prefix else f"z9hG4bK{rand}"


def _make_call_id(prefix: str = "") -> str:
    """生成全局唯一 Call-ID（RFC 3261 §20.8）。

    使用 64 位密码学随机值 @IP地址。
    FIX: [2026-07-22 P1] 忽略 prefix 参数（保留签名兼容现有调用点）。
    FIX: [2026-07-29 P0] Call-ID host 从 SIP_DOMAIN 改为 sip_via_host()（IP地址）。
    真实 GB28181 抓包显示 Call-ID host 均使用 IP 地址（如 @44.198.62.2），
    而非行政区划码。EasyGBS 对 @3402000000 的 Call-ID 可能返回 400。
    响应关联走 Via branch + XML SN，不依赖 Call-ID host 内容。
    """
    return f"{secrets.token_hex(8)}@{sip_via_host()}"


def _make_tag() -> str:
    """生成 From/To tag（RFC 3261 §19.3）。

    FIX: [2026-07-21 P0] 移除所有语义前缀（如 ptz/rec/di 等），仅使用 64 位密码学随机性。
    实测发现 EasyGBS 等非标准 SIP 客户端对带前缀的 tag 敏感，会返回 400 Bad Request。
    RFC 3261 §19.3 仅要求 tag 至少 32 位随机性，不要求语义前缀。
    """
    return secrets.token_hex(8)


def _attach_trace_header(req: SipMessage) -> str:
    """返回 Call-ID 作为 trace_id 用于日志关联。

    FIX: [2026-07-21 P0] 不再向 SIP 请求添加 X-Trace-ID 头域。
    实测发现 EasyGBS 等非标准 SIP 客户端对非标准头域（X- 开头）敏感，会返回 400 Bad Request，
    导致 catalog query / time sync 等所有 MESSAGE 请求失败、通道列表无法同步。
    RFC 3261 §20 允许扩展头域，但非标准头可能被严格实现拒绝。此处保留日志关联能力
    （通过返回 call_id 给调用方），但不再向 SIP 消息写入非标准头。

    FIX [2026-07-29 P0]: 添加 X-GB-Ver 头（GB28181 版本标识）。
    X-GB-Ver 是 GB/T 28181 标准扩展头（非自定义头），EasyGBS 自己的 REGISTER 包含此头。
    之前因担心 X- 头敏感而移除了所有 X- 头，但 X-GB-Ver 是 GB28181 标准头，应保留。
    """
    if not req.get_header("X-GB-Ver"):
        req.headers["X-GB-Ver"] = "3.0"
    return (req.get_header("Call-ID") or "").strip()


# GB28181 互操作性：UAC 应在请求中声明支持的方法集
_SIP_ALLOW_HEADER = "INVITE, ACK, CANCEL, BYE, OPTIONS, INFO, SUBSCRIBE, NOTIFY, MESSAGE, UPDATE"


def _attach_common_headers(req: SipMessage, device_id: str = "") -> None:
    """为 out-of-dialog SIP 请求补全 Contact 和 Allow 头（RFC 3261 §20.5/§20.10）。

    P0-fix: SUBSCRIBE 请求缺少 Contact 头会导致设备无法回送 NOTIFY；
    P1-fix: MESSAGE 请求缺少 Allow 头会影响互操作性判断。

    FIX: [2026-07-21 P0] 兼容非标准 SIP 客户端（如 EasyGBS 级联平台）：
    实测发现 EasyGBS 对 MESSAGE 请求中的 Contact/Allow 头域敏感，会返回 400 Bad Request，
    导致 catalog query 失败、通道列表无法同步。RFC 3261 §20.10 仅强制 INVITE 必须带 Contact，
    MESSAGE/OPTIONS/INFO 等方法不要求 Contact 和 Allow 头。此处对 MESSAGE 请求完全跳过
    Contact/Allow 头的补全，恢复 P1-fix 之前的行为，确保与各种非标准 SIP 客户端兼容。
    """
    _method = (getattr(req, "method", "") or "").strip().upper()
    # FIX: [2026-07-21 P0] MESSAGE 请求完全跳过 Contact/Allow 头，兼容 EasyGBS 等非标准客户端
    if _method == "MESSAGE":
        return
    if not req.get_header("Contact"):
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
    if not req.get_header("Allow"):
        req.headers["Allow"] = _SIP_ALLOW_HEADER

class SipCommander:
    def __init__(self, sip_server):
        self.sip_server = sip_server

    async def send_catalog_query(self, device_id: str, transport_info: tuple, wait_response: bool = False):
        """
        Send Catalog Query to device
        MESSAGE sip:device_id@ip:port SIP/2.0
        Content-Type: Application/MANSCDP+xml
        """
        addr, proto, transport = transport_info

        # Build XML Body
        sn = _next_sn()  # SN序列号使用递增计数器替代随机数
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>Catalog</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(device_id)}</DeviceID>
</Query>
"""

        # Create Request
        req = SipMessage()
        req.method = "MESSAGE"
        # FIX [2026-07-29 P0]: Request URI 使用 SIP_DOMAIN（GB28181 §9.2.1 标准），
        # 不用 IP:port。EasyGBS 自己的 REGISTER 也用 SIP_DOMAIN 作 request URI host。
        # 传输层使用 addr 参数发送，request URI 仅作逻辑地址。
        req.uri = f"sip:{device_id}@{settings.SIP_DOMAIN}"
        req.version = "SIP/2.0"

        # FIX: [2026-07-21 P0] 根据 RFC 3261 + GB28181 §9.2.1 规范统一头域格式
        # FIX [2026-07-29 P0]: From 用 IP（兼容 EasyGBS），To 用 SIP_DOMAIN（GB28181 标准）。
        # 之前 From 和 To 都用 sip_from_to_host()（PyGBSentry IP），导致 To 头的 host 是
        # 发送方 IP 而非 SIP_DOMAIN，EasyGBS 看到 To 头中自己的 ID 配了别人的 IP → 400。
        _from_host = sip_from_to_host()  # From 用 IP（EasyGBS 兼容）
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={_make_branch()}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{_from_host}>;tag={_make_tag()}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = _make_call_id()
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req)  # P0/P1-fix: 补全 Contact + Allow 头

        req.body = xml_body

        # Send
        data = req.to_bytes()
        # FIX: [2026-07-21 P0] 诊断 catalog query 完整请求内容
        # FIX [2026-07-29 P0]: 增加 hex dump 验证 CRLF 编码和 Content-Length 一致性
        try:
            _req_dump = data.decode("utf-8", errors="replace")
            _body_start = data.find(b"\r\n\r\n")
            _body_bytes = data[_body_start + 4:] if _body_start >= 0 else b""
            _cl_header = req.get_header("Content-Length") or "?"
            _hex_preview = _body_bytes[:60].hex(" ")
            logger.info(
                f"[CATALOG_DIAG] Sending Catalog Query to {device_id} via {addr} "
                f"(From host={_from_host}, To host={settings.SIP_DOMAIN}, CL={_cl_header}, body_len={len(_body_bytes)}, "
                f"body_hex={_hex_preview}):\n{_req_dump}"
            )
        except Exception as _diag_err:
            logger.debug(f"[CATALOG_DIAG] diagnostic log error: {_diag_err}")
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        if wait_response:
            from app.sip.transactions import tx_manager
            resp, meta = await tx_manager.send_and_wait(
                request=req,
                send_once=lambda: send_sip_bytes(proto, transport, addr, data),
                timeout_seconds=2.2,
                retries=1,
            )
            # W-02 send_and_wait超时时resp可能为None，访问前需空值检查
            _status_code = int(resp.status_code or 0) if resp else 0
            _rtt_ms = int(meta.get("rtt_ms") or 0) if meta else 0
            _attempts = int(meta.get("attempts") or 0) if meta else 0
            _sip_trace_log(
                "device_catalog_query_tx_ok",
                trace_id=req.get_header("Call-ID") or "",
                device_id=device_id,
                status_code=_status_code,
                rtt_ms=_rtt_ms,
                attempts=_attempts,
            )
            # FIX: [2026-07-21 P0] 记录 catalog query 响应（含非 200 的完整响应）
            if _status_code != 0 and _status_code != 200:
                try:
                    _resp_headers_dump = "; ".join(f"{k}: {v}" for k, v in resp.headers.raw_items()) if resp else ""
                    _resp_body_dump = ((resp.body or "")[:1000]) if resp else ""
                    logger.warning(
                        f"[CATALOG_DIAG] Non-200 response for Catalog Query to {device_id}: "
                        f"status={_status_code} rtt_ms={_rtt_ms} attempts={_attempts} "
                        f"headers=[{_resp_headers_dump}] body=[{_resp_body_dump}]"
                    )
                except Exception as _diag_err:
                    logger.debug(f"[CATALOG_DIAG] diagnostic log error: {_diag_err}")
        else:
            # SIP发送裸调用无异常保护
            try:
                await send_sip_bytes(proto, transport, addr, data)
            except Exception as e:
                logger.warning(f"Failed to send SIP Catalog to {addr}: {e}")
                return None

        logger.info(f"Sent Catalog Query to {device_id}")
        _sip_trace_log(
            "device_catalog_query_sent",
            trace_id=req.get_header("Call-ID") or "",
            device_id=device_id,
            proto=proto,
            addr=str(addr),
        )

    async def send_platform_catalog_query(self, platform_gb_id: str, transport_info: tuple):
        """
        Send Catalog Query to child platform.
        MESSAGE sip:platform_id@ip:port SIP/2.0
        Content-Type: Application/MANSCDP+xml
        """
        addr, proto, transport = transport_info
        sn = _next_sn()  # SN序列号使用递增计数器替代随机数
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>Catalog</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(platform_gb_id)}</DeviceID>
</Query>
"""

        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{platform_gb_id}@{settings.SIP_DOMAIN}"
        req.version = "SIP/2.0"

        # FIX: [2026-07-21 P0] 根据 RFC 3261 + GB28181 §9.2.1 规范统一头域格式
        _from_to_host = sip_from_to_host()
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={_make_branch()}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{_from_to_host}>;tag={_make_tag()}"
        req.headers["To"] = f"<sip:{platform_gb_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = _make_call_id('plat_cat')
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req)  # P0/P1-fix: 补全 Contact + Allow 头
        req.body = xml_body

        data = req.to_bytes()
        # FIX: [2026-07-21 P0] 诊断 platform catalog query 完整请求内容
        try:
            _req_dump = data.decode("utf-8", errors="replace")
            logger.info(
                f"[CATALOG_DIAG] Sending Platform Catalog Query to {platform_gb_id} via {addr} "
                f"(From host={_from_to_host}, To host={settings.SIP_DOMAIN}):\n{_req_dump}"
            )
        except Exception as _diag_err:
            logger.debug(f"[CATALOG_DIAG] diagnostic log error: {_diag_err}")
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        # SIP发送裸调用无异常保护
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send SIP PlatformCatalog to {addr}: {e}")
            return None

        logger.info(f"Sent Platform Catalog Query to {platform_gb_id}")
        _sip_trace_log(
            "platform_catalog_query_sent",
            trace_id=req.get_header("Call-ID") or "",
            platform_gb_id=platform_gb_id,
            proto=proto,
            addr=str(addr),
            sn=sn,
        )

    async def send_mobile_position_subscribe(self, device_id: str, transport_info: tuple, expires: int = 3600, interval: int = 60, wait_response: bool = False):
        """Send mobile position subscribe."""
        addr, proto, transport = transport_info
        sn = _next_sn()  # SN序列号使用递增计数器替代随机数

        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>MobilePosition</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(device_id)}</DeviceID>
<Interval>{interval}</Interval>
</Query>
"""
        req = SipMessage()
        req.method = "SUBSCRIBE"
        req.uri = f"sip:{device_id}@{settings.SIP_DOMAIN}"
        req.version = "SIP/2.0"

        # FIX: [2026-07-21 P0] 根据 RFC 3261 + GB28181 §9.2.1 规范统一头域格式
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={_make_branch()}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={_make_tag()}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = _make_call_id('sub')
        req.headers["CSeq"] = f"{_next_cseq()} SUBSCRIBE"
        req.headers["Event"] = "MobilePosition"
        req.headers["Expires"] = str(expires)
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req)  # P0/P1-fix: 补全 Contact + Allow 头

        req.body = xml_body
        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        if wait_response:
            from app.sip.transactions import tx_manager
            resp, meta = await tx_manager.send_and_wait(
                request=req,
                send_once=lambda: send_sip_bytes(proto, transport, addr, data),
                timeout_seconds=2.2,
                retries=1,
            )
            # W-02 send_and_wait超时时resp可能为None，访问前需空值检查
            _status_code = int(resp.status_code or 0) if resp else 0
            _rtt_ms = int(meta.get("rtt_ms") or 0) if meta else 0
            _attempts = int(meta.get("attempts") or 0) if meta else 0
            _sip_trace_log(
                "device_mobile_position_subscribe_tx_ok",
                trace_id=req.get_header("Call-ID") or "",
                device_id=device_id,
                status_code=_status_code,
                rtt_ms=_rtt_ms,
                attempts=_attempts,
            )
        else:
            # SIP发送裸调用无异常保护
            try:
                await send_sip_bytes(proto, transport, addr, data)
            except Exception as e:
                logger.warning(f"Failed to send SIP MobilePosition to {addr}: {e}")
                return None

        logger.info(f"Sent MobilePosition SUBSCRIBE to {device_id} with expires={expires}, interval={interval}")
        _sip_trace_log(
            "device_mobile_position_subscribe_sent",
            trace_id=req.get_header("Call-ID") or "",
            device_id=device_id,
            proto=proto,
            addr=str(addr),
            interval=interval,
            expires=expires,
        )

    async def send_time_sync(self, device_id: str, transport_info: tuple):
        """
        """
        from app.core.timezone import now_in_app_timezone
        addr, proto, transport = transport_info
        sn = _next_sn()  # SN序列号使用递增计数器替代随机数
        # FIX: [2026-07-17 P1] 统一使用应用时区，与 send_platform_time_sync 保持一致
        # GB28181-2016 §A.4.2 规定 TimeSync 的 Time 字段应使用本地时间
        now = now_in_app_timezone()
        time_str = now.strftime("%Y-%m-%dT%H:%M:%S")
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Notify>
<CmdType>TimeSync</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(settings.SIP_ID)}</DeviceID>
<Time>{time_str}</Time>
</Notify>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{settings.SIP_DOMAIN}"
        req.version = "SIP/2.0"
        # FIX: [2026-07-21 P0] 根据 RFC 3261 + GB28181 §9.2.1 规范统一头域格式
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={_make_branch()}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={_make_tag()}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = _make_call_id('ts')
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # FIX R23-SEVERE: 使用 _next_cseq() 替代硬编码 CSeq
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req)  # P0/P1-fix: 补全 Contact + Allow 头
        req.body = xml_body
        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        # SIP发送裸调用无异常保护
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send SIP TimeSync to {addr}: {e}")
            return None
        logger.info(f"Sent TimeSync to {device_id} at {time_str}")
        _sip_trace_log(
            "device_time_sync_sent",
            trace_id=req.get_header("Call-ID") or "",
            device_id=device_id,
            proto=proto,
            addr=str(addr),
            time=time_str,
        )

    async def send_ptz_cmd(self, device_id: str, channel_id: str, transport_info: tuple,
                           left_right: int, up_down: int, in_out: int, move_speed: int = 127, zoom_speed: int = 16) -> bool:
        """R24-03: 返回 bool 表示 SIP 发送是否成功，避免静默丢失 PTZ 命令。"""
        move_speed = max(0, min(255, int(move_speed or 0)))
        zoom_speed = max(0, min(255, int(zoom_speed or 0)))
        left_right = max(0, min(2, int(left_right or 0)))
        up_down = max(0, min(2, int(up_down or 0)))
        in_out = max(0, min(2, int(in_out or 0)))

        cmd_code = 0
        if left_right == 2:
            cmd_code |= 0x01
        elif left_right == 1:
            cmd_code |= 0x02

        if up_down == 2:
            cmd_code |= 0x04
        elif up_down == 1:
            cmd_code |= 0x08

        if in_out == 2:
            cmd_code |= 0x10
        elif in_out == 1:
            cmd_code |= 0x20

        # PTZ Hex calculation
        # A5 0F 01 cmd_code move_speed move_speed (zoom_speed & 0xF0) check_code
        # zoom_speed 有效范围 1-15，低4位放在高4位位?(左移4?
        # 0值会导致无缩放指令，故最小设?
        if zoom_speed < 1:
            zoom_hex = 0
        else:
            zoom_hex = min(zoom_speed, 15) << 4
        check_code = (0xA5 + 0x0F + 0x01 + cmd_code + move_speed + move_speed + zoom_hex) % 0x100

        ptz_cmd = f"A50F01{cmd_code:02X}{move_speed:02X}{move_speed:02X}{zoom_hex:02X}{check_code:02X}"

        addr, proto, transport = transport_info
        sn = _next_sn()  # SN序列号使用递增计数器替代随机数

        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<PTZCmd>{ptz_cmd}</PTZCmd>
<Info>
<ControlPriority>5</ControlPriority>
</Info>
</Control>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{settings.SIP_DOMAIN}"
        req.version = "SIP/2.0"

        # FIX: [2026-07-21 P0] 根据 RFC 3261 + GB28181 §9.2.1 规范统一头域格式
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={_make_branch()}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={_make_tag()}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = _make_call_id('ptz')
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # FIX R23-SEVERE: 使用 _next_cseq() 替代硬编码 CSeq
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req)  # P0/P1-fix: 补全 Contact + Allow 头

        req.body = xml_body
        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        # R24-03: send_sip_bytes 已返回 bool，调用方据此判断发送成败
        sent_ok = await send_sip_bytes(proto, transport, addr, data)
        if not sent_ok:
            logger.warning(f"Failed to send SIP PTZCmd to {addr} (send_sip_bytes returned False)")
            return False
        logger.info(f"Sent PTZ Cmd to {channel_id} (device: {device_id}), PTZ={ptz_cmd}")
        _sip_trace_log(
            "device_ptz_cmd_sent",
            trace_id=req.get_header("Call-ID") or "",
            device_id=device_id,
            channel_id=channel_id,
            ptz_cmd=ptz_cmd,
            proto=proto,
            addr=str(addr),
        )
        return True

    async def send_absolute_ptz_cmd(self, device_id: str, channel_id: str, transport_info: tuple, pan: float, tilt: float, zoom: float) -> bool:
        """
        GB/T 28181-2022 绝对云台控制 (Absolute PTZ)
        pan: 水平角度
        tilt: 垂直角度
        zoom: 缩放倍数
        """
        addr, proto, transport = transport_info
        sn = _next_sn()  # SN序列号使用递增计数器替代随机数

        pan_val = max(0, min(int(pan), 360))
        tilt_val = max(0, min(int(tilt), 180))
        zoom_val = max(0, min(int(zoom * 16), 255))

        ptz_cmd = f"A50F81{pan_val:02X}{tilt_val:02X}{zoom_val:02X}00{(0xA5 + 0x0F + 0x81 + pan_val + tilt_val + zoom_val) % 0x100:02X}"

        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<PTZCmd>{ptz_cmd}</PTZCmd>
<Info>
<ControlPriority>5</ControlPriority>
</Info>
</Control>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{settings.SIP_DOMAIN}"
        req.version = "SIP/2.0"

        # FIX: [2026-07-21 P0] 根据 RFC 3261 + GB28181 §9.2.1 规范统一头域格式
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={_make_branch()}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={_make_tag()}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = _make_call_id('absptz')
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # FIX R23-SEVERE: 使用 _next_cseq() 替代硬编码 CSeq
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req)  # P0/P1-fix: 补全 Contact + Allow 头

        req.body = xml_body
        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        # R24-03: send_sip_bytes 返回 bool，失败时调用方应感知
        sent_ok = await send_sip_bytes(proto, transport, addr, data)
        if not sent_ok:
            logger.warning(f"Failed to send SIP AbsolutePTZ to {addr} (send_sip_bytes returned False)")
            return False
        logger.info(f"Sent Absolute PTZ Cmd to {channel_id} (device: {device_id}), pan={pan} tilt={tilt} zoom={zoom}")
        _sip_trace_log(
            "device_absolute_ptz_cmd_sent",
            trace_id=req.get_header("Call-ID") or "",
            device_id=device_id,
            channel_id=channel_id,
            pan=pan,
            tilt=tilt,
            zoom=zoom,
            proto=proto,
            addr=str(addr),
        )
        return True

    async def send_raw_ptz_cmd(self, device_id: str, channel_id: str, transport_info: tuple, ptz_cmd: str) -> bool:
        """
        """
        addr, proto, transport = transport_info
        sn = _next_sn()  # SN序列号使用递增计数器替代随机数

        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<PTZCmd>{ptz_cmd}</PTZCmd>
<Info>
<ControlPriority>5</ControlPriority>
</Info>
</Control>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{settings.SIP_DOMAIN}"
        req.version = "SIP/2.0"

        # FIX: [2026-07-21 P0] 根据 RFC 3261 + GB28181 §9.2.1 规范统一头域格式
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={_make_branch()}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={_make_tag()}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = _make_call_id('ptz')
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # FIX R23-SEVERE: 使用 _next_cseq() 替代硬编码 CSeq
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req)  # P0/P1-fix: 补全 Contact + Allow 头

        req.body = xml_body
        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        # R24-03: send_sip_bytes 返回 bool，预置位命令失败需明确感知
        sent_ok = await send_sip_bytes(proto, transport, addr, data)
        if not sent_ok:
            logger.warning(f"Failed to send SIP RawPTZ to {addr} (send_sip_bytes returned False)")
            return False
        logger.info(f"Sent Raw PTZ Cmd to {channel_id} (device: {device_id}), PTZ={ptz_cmd}")
        return True

    async def send_record_info_query(self, device_id: str, channel_id: str, transport_info: tuple,
                                     start_time: str, end_time: str, record_type: str = "all", wait_response: bool = False):
        """
        发送录像文件查?(RecordInfo)
        """
        addr, proto, transport = transport_info
        sn = _next_sn()  # SN序列号使用递增计数器替代随机数

        # 兼容部分 NVR，比如大华需?Type=all
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>RecordInfo</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
<StartTime>{start_time}</StartTime>
<EndTime>{end_time}</EndTime>
<Secrecy>0</Secrecy>
<Type>{record_type}</Type>
</Query>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{settings.SIP_DOMAIN}"
        req.version = "SIP/2.0"

        # FIX: [2026-07-21 P0] 根据 RFC 3261 + GB28181 §9.2.1 规范统一头域格式
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={_make_branch()}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={_make_tag()}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = _make_call_id("rec")
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # FIX R23-SEVERE: 使用 _next_cseq() 替代硬编码 CSeq
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req)  # P0/P1-fix: 补全 Contact + Allow 头

        req.body = xml_body
        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志

        if wait_response:
            from app.sip.transactions import tx_manager
            resp, meta = await tx_manager.send_and_wait(
                request=req,
                send_once=lambda: send_sip_bytes(proto, transport, addr, data),
                timeout_seconds=2.2,
                retries=1,
            )
            # W-02 send_and_wait超时时resp可能为None，访问前需空值检查
            _status_code = int(resp.status_code or 0) if resp else 0
            _rtt_ms = int(meta.get("rtt_ms") or 0) if meta else 0
            _sip_trace_log(
                "device_record_info_query_tx_ok",
                trace_id=req.get_header("Call-ID") or "",
                device_id=device_id,
                channel_id=channel_id,
                status_code=_status_code,
                rtt_ms=_rtt_ms,
            )
            return str(sn)
        else:
            # SIP发送裸调用无异常保护
            try:
                await send_sip_bytes(proto, transport, addr, data)
            except Exception as e:
                logger.warning(f"Failed to send SIP RecordInfo to {addr}: {e}")
                return None

        logger.info(f"Sent RecordInfo Query to {channel_id} (device: {device_id})")
        _sip_trace_log(
            "device_record_info_query_sent",
            trace_id=req.get_header("Call-ID") or "",
            device_id=device_id,
            channel_id=channel_id,
            proto=proto,
            addr=str(addr),
            sn=sn,
        )
        return str(sn)

    async def send_stream_control(self, device_id: str, channel_id: str, transport_info: tuple,
                                  action: str, stream_session: dict, speed: float = 1.0, seek_time: int = 0):
        """
        发?INFO 录像流控指令: action IN (PAUSE, PLAY, TEARDOWN)
        """
        addr, proto, transport = transport_info

        cseq = _next_cseq()

        if action.upper() == "PAUSE":
            content = f"PAUSE RTSP/1.0\r\nCSeq: {cseq}\r\nPauseTime: now\r\n"
        elif action.upper() == "PLAY":
            if speed != 1.0:
                content = f"PLAY RTSP/1.0\r\nCSeq: {cseq}\r\nScale: {speed:.6f}\r\n"
            elif seek_time > 0:
                content = f"PLAY RTSP/1.0\r\nCSeq: {cseq}\r\nRange: npt={seek_time}-\r\n"
            else:
                content = f"PLAY RTSP/1.0\r\nCSeq: {cseq}\r\nRange: npt=now-\r\n"
        elif action.upper() == "TEARDOWN":
            content = f"TEARDOWN RTSP/1.0\r\nCSeq: {cseq}\r\n"
        else:
            return

        req = SipMessage()
        req.method = "INFO"
        req.uri = f"sip:{channel_id}@{settings.SIP_DOMAIN}"
        req.version = "SIP/2.0"

        # P0-fix [2026-07-17]: branch 必须使用 64 位密码学随机值（RFC 3261 §8.1.1.7）
        # FIX: [2026-07-21 P0] branch 不带 prefix，统一规范（RFC 3261 + GB28181 §9.2.1）
        branch = _make_branch()
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"

        # Use existing dialog tags
        from_tag = stream_session.get("from_tag", "")
        to_tag = stream_session.get("to_tag", "")
        call_id = stream_session.get("call_id", "")

        # FIX: [2026-07-21 P0] From URI host 使用 sip_from_to_host() (IP)
        # FIX [2026-07-29 P0]: To URI host 使用 SIP_DOMAIN（GB28181 标准），
        # 之前 To 也用 sip_from_to_host()（发送方 IP），EasyGBS 会 400。
        # in-dialog 请求的 from_tag/to_tag/call_id 必须保留原值（RFC 3261 §12.2）
        _ft_host = sip_from_to_host()  # From 用 IP（EasyGBS 兼容）
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{_ft_host}>;tag={from_tag}"
        if to_tag:
            req.headers["To"] = f"<sip:{channel_id}@{settings.SIP_DOMAIN}>;tag={to_tag}"
        else:
            req.headers["To"] = f"<sip:{channel_id}@{settings.SIP_DOMAIN}>"

        req.headers["Call-ID"] = call_id
        # CSeq sequence number must be higher than previous, we use a random large one here for INFO
        req.headers["CSeq"] = f"{cseq} INFO"
        req.headers["Content-Type"] = "Application/MANSRTSP"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req)  # P0/P1-fix: 补全 Contact + Allow 头

        req.body = content
        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志

        # SIP发送裸调用无异常保护
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send SIP StreamControl to {addr}: {e}")
            return None
        logger.info(f"Sent INFO stream control {action} to {channel_id}")

    async def send_broadcast(self, device_id: str, channel_id: str, transport_info: tuple):
        """
        发送语音广播请?(Broadcast)
        """
        addr, proto, transport = transport_info
        sn = _next_sn()  # SN序列号使用递增计数器替代随机数

        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Notify>
<CmdType>Broadcast</CmdType>
<SN>{sn}</SN>
<SourceID>{_xml_escape(settings.SIP_ID)}</SourceID>
<TargetID>{_xml_escape(channel_id)}</TargetID>
</Notify>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{settings.SIP_DOMAIN}"
        req.version = "SIP/2.0"

        # FIX: [2026-07-21 P0] 根据 RFC 3261 + GB28181 §9.2.1 规范统一头域格式
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={_make_branch()}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={_make_tag()}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = _make_call_id('bc')
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # FIX R23-SEVERE: 使用 _next_cseq() 替代硬编码 CSeq
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req)  # P0/P1-fix: 补全 Contact + Allow 头

        req.body = xml_body
        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        # SIP发送裸调用无异常保护
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send SIP Broadcast to {addr}: {e}")
            return None
        logger.info(f"Sent Broadcast Notify to {channel_id} (device: {device_id})")

    async def send_catalog_subscribe(self, device_id: str, transport_info: tuple, expires: int = 3600):
        """
        发送设备目录订?(Catalog Subscribe)
        """
        addr, proto, transport = transport_info
        sn = _next_sn()  # SN序列号使用递增计数器替代随机数

        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>Catalog</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(device_id)}</DeviceID>
</Query>
"""
        req = SipMessage()
        req.method = "SUBSCRIBE"
        req.uri = f"sip:{device_id}@{settings.SIP_DOMAIN}"
        req.version = "SIP/2.0"

        # FIX: [2026-07-21 P0] 根据 RFC 3261 + GB28181 §9.2.1 规范统一头域格式
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={_make_branch()}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={_make_tag()}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = _make_call_id('sub')
        req.headers["CSeq"] = f"{_next_cseq()} SUBSCRIBE"
        req.headers["Event"] = "catalog"
        req.headers["Expires"] = str(expires)
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req)  # P0/P1-fix: 补全 Contact + Allow 头

        req.body = xml_body
        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        # SIP发送裸调用无异常保护
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send SIP CatalogSubscribe to {addr}: {e}")
            return None
        logger.info(f"Sent Catalog Subscribe to {device_id} with expires={expires}")

    async def send_alarm_subscribe(
        self,
        device_id: str,
        gb_domain: str,
        sip_id: str,
        sip_domain: str,
        device_host: str,
        device_port: int,
        expires: int = 3600,
        transport: str = "udp",
    ) -> str:
        """发送 Alarm 事件订阅 (SUBSCRIBE Event: Alarm)"""
        # 实现报警订阅发送
        from app.sip.server import sip_server

        proto = transport.upper()
        addr = (device_host, device_port)
        _transport = sip_server.get_transport(addr[0], addr[1], proto)
        if not _transport:
            logger.warning(f"[SipCommander] No transport for Alarm subscribe to {device_id}")
            return ""

        sn = _next_sn()  # SN序列号使用递增计数器替代随机数
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>Alarm</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(device_id)}</DeviceID>
</Query>
"""
        req = SipMessage()
        req.method = "SUBSCRIBE"
        req.uri = f"sip:{device_id}@{settings.SIP_DOMAIN}"
        req.version = "SIP/2.0"

        # FIX: [2026-07-21 P0] 根据 RFC 3261 + GB28181 §9.2.1 规范统一头域格式
        # From URI host: settings.SIP_DOMAIN（行政区划码，GB28181 §9.2.1 要求）
        # To URI host: settings.SIP_DOMAIN（保持一致）
        # sip_id 参数保留用于 From URI 的 user 部分
        branch = _make_branch()
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{sip_id}@{sip_from_to_host()}>;tag={_make_tag()}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = _make_call_id('alarm')
        req.headers["CSeq"] = f"{_next_cseq()} SUBSCRIBE"
        req.headers["Event"] = "Alarm"
        req.headers["Expires"] = str(expires)
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req)  # P0/P1-fix: 补全 Contact + Allow 头

        req.body = xml_body
        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        # SIP发送裸调用无异常保护
        try:
            await send_sip_bytes(proto, _transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send SIP AlarmSubscribe to {addr}: {e}")
            return ""
        logger.info(f"Sent Alarm SUBSCRIBE to {device_id} with expires={expires}")
        _sip_trace_log(
            "device_alarm_subscribe_sent",
            trace_id=req.get_header("Call-ID") or "",
            device_id=device_id,
            proto=proto,
            addr=str(addr),
            expires=expires,
        )
        return req.get_header("Call-ID") or ""

    async def send_config_upload(self, device_id, channel_id, transport_info, config_type="BasicParam", config_data=""):
        """发送设备配置设置/下发 (ConfigUpload)"""
        # 实现ConfigUpload设备配置设置/下发
        from app.sip.device_control import device_control
        if device_control:
            return await device_control.send_config_upload(
                device_id=device_id, channel_id=channel_id,
                transport_info=transport_info, config_type=config_type,
                config_data=config_data,
            )

    async def send_config_download(self, device_id, channel_id, transport_info, config_type="BasicParam"):
        """发送配置下载查询"""
        # 实现 GB28181-2022 配置下载查询
        from app.sip.device_control import device_control
        if device_control:
            return await device_control.send_config_download(
                device_id=device_id, channel_id=channel_id,
                transport_info=transport_info, config_type=config_type,
            )

    async def send_preset_query(self, device_id, channel_id, transport_info):
        """发送预置位查询"""
        # 预置位查询桥接，与wvp对齐
        from app.sip.device_control import device_control
        if device_control:
            return await device_control.send_preset_query(
                device_id=device_id, channel_id=channel_id,
                transport_info=transport_info,
            )

    async def send_config_set(self, device_id, channel_id, transport_info, config_type="BasicParam", config_params=None):
        """发送配置设置命令"""
        # 实现 GB28181-2022 配置设置
        from app.sip.device_control import device_control
        if device_control:
            return await device_control.send_config_set(
                device_id=device_id, channel_id=channel_id,
                transport_info=transport_info, config_type=config_type,
                config_params=config_params,
            )

    async def send_device_info_query(self, device_id, transport_info):
        """发送设备信息查询 (CmdType=DeviceInfo)"""
        # 实现设备信息查询
        addr, proto, transport = transport_info
        sn = _next_sn()  # SN序列号使用递增计数器替代随机数
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>DeviceInfo</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(device_id)}</DeviceID>
</Query>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{settings.SIP_DOMAIN}"
        req.version = "SIP/2.0"

        # FIX: [2026-07-21 P0] 根据 RFC 3261 + GB28181 §9.2.1 规范统一头域格式
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={_make_branch()}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={_make_tag()}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = _make_call_id('di')
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req)  # P0/P1-fix: 补全 Contact + Allow 头

        req.body = xml_body
        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        # SIP发送裸调用无异常保护
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send SIP DeviceInfo to {addr}: {e}")
            return None
        logger.info(f"Sent DeviceInfo Query to {device_id}")
        _sip_trace_log(
            "device_info_query_sent",
            trace_id=req.get_header("Call-ID") or "",
            device_id=device_id,
            proto=proto,
            addr=str(addr),
        )
        return str(sn)

    async def send_directory_query(self, device_id: str, transport_info: tuple,
                                   parent_directory_id: str = "", begin_time: str = "", end_time: str = ""):
        """
        # GB28181-2022 文件目录检索
        发送文件目录检索查询 (CmdType=QueryDirectory)
        """
        addr, proto, transport = transport_info
        sn = _next_sn()  # SN序列号使用递增计数器替代随机数

        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>QueryDirectory</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(device_id)}</DeviceID>
"""
        if parent_directory_id:
            xml_body += f"<ParentDirectoryID>{_xml_escape(parent_directory_id)}</ParentDirectoryID>\n"
        if begin_time:
            xml_body += f"<BeginTime>{_xml_escape(begin_time)}</BeginTime>\n"
        if end_time:
            xml_body += f"<EndTime>{_xml_escape(end_time)}</EndTime>\n"
        xml_body += "</Query>\n"

        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{settings.SIP_DOMAIN}"
        req.version = "SIP/2.0"

        # FIX: [2026-07-21 P0] 根据 RFC 3261 + GB28181 §9.2.1 规范统一头域格式
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={_make_branch()}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={_make_tag()}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = _make_call_id('dir')
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req)  # P0/P1-fix: 补全 Contact + Allow 头

        req.body = xml_body
        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        # SIP发送裸调用无异常保护
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send SIP QueryDirectory to {addr}: {e}")
            return None
        logger.info(f"Sent QueryDirectory to {device_id}")
        _sip_trace_log(
            "device_directory_query_sent",
            trace_id=req.get_header("Call-ID") or "",
            device_id=device_id,
            proto=proto,
            addr=str(addr),
            parent_directory_id=parent_directory_id,
        )
        return str(sn)

    async def send_alarm_code_query(self, device_id: str, transport_info: tuple, alarm_code_type: str = "1"):
        """
        # GB28181-2022 布防报警细化分类查询
        发送布防报警分类查询 (CmdType=AlarmCodeQuery)
        alarm_code_type: 报警分类类型(1=报警设备类型, 2=报警方式)
        """
        addr, proto, transport = transport_info
        sn = _next_sn()  # SN序列号使用递增计数器替代随机数

        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>AlarmCodeQuery</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(device_id)}</DeviceID>
<AlarmCodeType>{_xml_escape(alarm_code_type)}</AlarmCodeType>
</Query>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{settings.SIP_DOMAIN}"
        req.version = "SIP/2.0"

        # FIX: [2026-07-21 P0] 根据 RFC 3261 + GB28181 §9.2.1 规范统一头域格式
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={_make_branch()}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={_make_tag()}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = _make_call_id("ac")
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req)  # P0/P1-fix: 补全 Contact + Allow 头

        req.body = xml_body
        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        # SIP发送裸调用无异常保护
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send SIP AlarmCodeQuery to {addr}: {e}")
            return None
        logger.info(f"Sent AlarmCodeQuery to {device_id}")
        _sip_trace_log(
            "device_alarm_code_query_sent",
            trace_id=req.get_header("Call-ID") or "",
            device_id=device_id,
            proto=proto,
            addr=str(addr),
            alarm_code_type=alarm_code_type,
        )
        return str(sn)

    async def send_device_status_query(self, device_id, transport_info):
        """发送设备状态查询 (CmdType=DeviceStatus)"""
        # 实现设备状态查询
        addr, proto, transport = transport_info
        sn = _next_sn()  # SN序列号使用递增计数器替代随机数
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>DeviceStatus</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(device_id)}</DeviceID>
</Query>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{settings.SIP_DOMAIN}"
        req.version = "SIP/2.0"

        # FIX: [2026-07-21 P0] 根据 RFC 3261 + GB28181 §9.2.1 规范统一头域格式
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={_make_branch()}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={_make_tag()}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = _make_call_id('ds')
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req)  # P0/P1-fix: 补全 Contact + Allow 头

        req.body = xml_body
        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        # SIP发送裸调用无异常保护
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send SIP DeviceStatus to {addr}: {e}")
            return None
        logger.info(f"Sent DeviceStatus Query to {device_id}")
        _sip_trace_log(
            "device_status_query_sent",
            trace_id=req.get_header("Call-ID") or "",
            device_id=device_id,
            proto=proto,
            addr=str(addr),
        )
        return str(sn)

    async def send_platform_time_sync(self, device_id: str, transport_info: tuple) -> bool:
        """GB28181 TimeSync — 向设备发送时间同步请求"""
        # GB28181协议 — 实现平台间时间同步
        from app.core.timezone import now_in_app_timezone
        addr, proto, transport = transport_info
        # FIX: [2026-07-17 P1] 统一使用应用时区，与 send_time_sync 保持一致
        now = now_in_app_timezone()
        time_str = now.strftime("%Y-%m-%dT%H:%M:%S")
        sn = _next_sn()
        # P1-fix: GB/T 28181-2022 §A.4.2 规定 TimeSync 命令应使用 <Notify> 根元素，与 send_time_sync 保持一致
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Notify>
<CmdType>TimeSync</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(device_id)}</DeviceID>
<Time>{time_str}</Time>
</Notify>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{settings.SIP_DOMAIN}"
        req.version = "SIP/2.0"
        # FIX: [2026-07-21 P0] 根据 RFC 3261 + GB28181 §9.2.1 规范统一头域格式
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={_make_branch()}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={_make_tag()}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = _make_call_id("pts")
        req.headers["CSeq"] = f"{_next_cseq()} MESSAGE"  # FIX R23-SEVERE: 使用 _next_cseq() 替代硬编码 CSeq
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        _attach_common_headers(req)  # P0/P1-fix: 补全 Contact + Allow 头
        req.body = xml_body
        data = req.to_bytes()
        fire_and_forget(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))  # P0-16: 保存引用防 GC + 异常日志
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send SIP PlatformTimeSync to {addr}: {e}")
            return False
        logger.info(f"Sent PlatformTimeSync to {device_id} at {time_str}")
        _sip_trace_log(
            "platform_time_sync_sent",
            trace_id=req.get_header("Call-ID") or "",
            device_id=device_id,
            proto=proto,
            addr=str(addr),
            time=time_str,
        )
        return True

# Singleton will be initialized in main.py
sip_commander = None
