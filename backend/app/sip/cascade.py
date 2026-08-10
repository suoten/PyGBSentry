"""
Cascade module - thin proxy delegating to PlatformService.

All cascade functionality (registration, keepalive, catalog push, INVITE response,
alarm notify) has been consolidated into PlatformService. This module provides
backward-compatible aliases so that existing import paths continue to work.
"""
from __future__ import annotations

import time  # N-01 _cleanup_stale_call_ids使用time.time()但未导入
import secrets

from loguru import logger
from app.sip.message import SipMessage
from app.models.platform import ParentPlatform


def _get_svc():
    """Get the PlatformService singleton."""
    import app.services.platform_service as _mod
    return getattr(_mod, "platform_service", None)


class SipCascadeCommander:
    """Backward-compatible proxy that delegates all calls to PlatformService."""

    def __init__(self):
        # GB8 级联事务跟踪 — 记录级联REGISTER的Call-ID
        self._cascade_call_ids: set[str] = set()
        self._cascade_call_id_timestamps: dict[str, float] = {}  # W-18 记录call_id时间戳，用于TTL清理

    def _cleanup_stale_call_ids(self, max_age: float = 60.0) -> None:
        """W-18 清理超过max_age秒的call_id，防止内存泄漏"""
        now = time.time()
        stale = [k for k, ts in self._cascade_call_id_timestamps.items() if now - ts > max_age]
        for k in stale:
            self._cascade_call_ids.discard(k)
            self._cascade_call_id_timestamps.pop(k, None)

    async def start_platform(self, platform: ParentPlatform) -> None:
        """Delegate: trigger register via PlatformService."""
        svc = _get_svc()
        if svc and getattr(svc, "running", False):
            await svc.trigger_register(str(platform.id))

    async def stop_platform(self, platform_id: str) -> None:
        """Delegate: handle platform offline via PlatformService."""
        svc = _get_svc()
        if svc and getattr(svc, "running", False):
            await svc.handle_platform_offline(platform_id, reason="cascade_stop")

    async def start_all(self) -> None:
        """No-op: PlatformService._run_loop already handles auto-discovery."""
        logger.debug("[CascadeProxy] start_all is a no-op; PlatformService manages platform lifecycle")

    async def stop_all(self) -> None:
        """No-op: PlatformService.stop() is called from main.py shutdown."""
        logger.debug("[CascadeProxy] stop_all is a no-op; PlatformService manages platform lifecycle")

    def handle_any_response(self, message: SipMessage, addr: tuple = None, proto: str = "", transport=None) -> bool:
        """Handle cascade SIP responses. GB8 级联响应处理"""
        call_id = str(getattr(message, "call_id", "") or "")
        # Check if this call_id belongs to a cascade transaction
        if call_id and call_id in self._cascade_call_ids:
            status_code = int(getattr(message, "status_code", 0) or 0)
            logger.info(f"Cascade response: {status_code} for Call-ID={call_id}")
            # Handle 401 challenge for cascade REGISTER
            if status_code == 401:
                www_auth = message.get_header("WWW-Authenticate") or ""
                if www_auth:
                    # GB8 处理401摘要认证挑战 — 委托给PlatformService重新注册
                    logger.info(f"Cascade REGISTER received 401 challenge for Call-ID={call_id}, delegating to PlatformService")
                    # PlatformService._handle_response already handles 401 re-registration
            # Clean up completed cascade transactions
            if 200 <= status_code <= 699:
                self._cascade_call_ids.discard(call_id)
            return True
        return False

    async def send_register(self, platform: ParentPlatform, expires: int = 3600, auth_params: dict = None) -> None:
        """Delegate: trigger register via PlatformService."""
        svc = _get_svc()
        if svc and getattr(svc, "running", False):
            await svc.trigger_register(str(platform.id))

    async def send_cascade_register(self, platform_config: dict) -> bool:
        """Send REGISTER to upstream platform. GB8 上级平台级联注册"""
        from app.core.config import settings, sip_host_for_contact, sip_via_host, sip_from_to_host
        from app.sip.send import send_sip_bytes
        from app.sip.server import sip_server

        server_gb_id = platform_config.get("server_gb_id", "")
        server_domain = platform_config.get("server_domain", "") or settings.SIP_DOMAIN
        server_ip = platform_config.get("server_ip", "")
        server_port = int(platform_config.get("server_port", 5060))
        username = platform_config.get("username", "") or platform_config.get("client_gb_id", "")
        platform_config.get("password", "")
        expires_val = int(platform_config.get("expires", 3600))
        proto = str(platform_config.get("transport", "UDP") or "UDP").upper()

        if not server_gb_id or not server_ip:
            logger.error("Cascade register: missing server_gb_id or server_ip")
            return False

        addr = (server_ip, server_port)
        transport = sip_server.get_transport(server_ip, server_port, proto)
        if not transport:
            logger.error(f"Cascade register: no transport to {server_ip}:{server_port}")
            return False

        # Build REGISTER request
        req = SipMessage()
        req.method = "REGISTER"
        req.uri = f"sip:{server_gb_id}@{server_domain}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(8)}"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        from_tag = secrets.token_hex(8)  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §19.3）
        req.headers["From"] = f"<sip:{username}@{sip_from_to_host()}>;tag={from_tag}"
        # R-05 级联REGISTER的To头使用目标平台域(RFC 3261/GB28181)，而非本地域
        req.headers["To"] = f"<sip:{server_gb_id}@{server_domain}>"
        call_id = f"cascade_{secrets.token_hex(8)}@{sip_via_host()}"
        req.headers["Call-ID"] = call_id
        # FIX [2026-07-17 P1]: CSeq 必须单调递增（RFC 3261 §22.2），原硬编码 "1 REGISTER"
        # 会导致级联重注册时 CSeq 冲突，上级平台可能拒绝后续 REGISTER。
        from app.sip.commander import _next_cseq as _cascade_next_cseq
        req.headers["CSeq"] = f"{_cascade_next_cseq()} REGISTER"
        req.headers["Contact"] = f"<sip:{username}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Expires"] = str(expires_val)
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME

        # Track this cascade transaction
        self._cascade_call_ids.add(call_id)
        self._cascade_call_id_timestamps[call_id] = time.time()  # W-18
        self._cleanup_stale_call_ids()  # W-18

        try:
            await send_sip_bytes(proto, transport, addr, req.to_bytes())
            logger.info(f"Cascade REGISTER sent to {server_gb_id}@{server_ip}:{server_port}, Call-ID={call_id}")
        except Exception as e:
            logger.error(f"Cascade REGISTER send failed: {e}")
            self._cascade_call_ids.discard(call_id)
            return False

        return True

    async def send_cascade_catalog_query(self, platform_config: dict, device_id: str = ""):
        """Query catalog from upstream platform. GB8 级联目录同步"""
        from app.core.config import settings, sip_via_host, sip_from_to_host
        from app.sip.send import send_sip_bytes
        from app.sip.server import sip_server

        server_gb_id = platform_config.get("server_gb_id", "")
        server_domain = platform_config.get("server_domain", "") or settings.SIP_DOMAIN
        server_ip = platform_config.get("server_ip", "")
        server_port = int(platform_config.get("server_port", 5060))
        username = platform_config.get("username", "") or platform_config.get("client_gb_id", "")
        proto = str(platform_config.get("transport", "UDP") or "UDP").upper()

        if not server_gb_id or not server_ip:
            logger.error("Cascade catalog query: missing server_gb_id or server_ip")
            return

        addr = (server_ip, server_port)
        transport = sip_server.get_transport(server_ip, server_port, proto)
        if not transport:
            logger.error(f"Cascade catalog query: no transport to {server_ip}:{server_port}")
            return

        target_device = device_id or server_gb_id
        sn = secrets.randbelow(65535) + 1  # C-26 random.randint→secrets，与项目安全规范一致
        xml_body = (
            '<?xml version="1.0" encoding="GB2312"?>\n'
            '<Query>\n'
            '<CmdType>Catalog</CmdType>\n'
            f'<SN>{sn}</SN>\n'
            f'<DeviceID>{target_device}</DeviceID>\n'
            '</Query>'
        )

        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{server_gb_id}@{server_domain}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(8)}"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        from_tag = secrets.token_hex(8)  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §19.3）
        req.headers["From"] = f"<sip:{username}@{sip_from_to_host()}>;tag={from_tag}"
        req.headers["To"] = f"<sip:{server_gb_id}@{server_domain}>"
        call_id = f"cascade_cat_{secrets.token_hex(8)}@{sip_via_host()}"
        req.headers["Call-ID"] = call_id
        # FIX [2026-07-17 P1]: CSeq 单调递增（RFC 3261 §22.2）
        from app.sip.commander import _next_cseq as _cascade_next_cseq
        req.headers["CSeq"] = f"{_cascade_next_cseq()} MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.body = xml_body

        # Track this cascade transaction
        self._cascade_call_ids.add(call_id)
        self._cascade_call_id_timestamps[call_id] = time.time()  # W-18
        self._cleanup_stale_call_ids()  # W-18

        try:
            await send_sip_bytes(proto, transport, addr, req.to_bytes())
            logger.info(f"Cascade catalog query sent to {server_gb_id}@{server_ip}:{server_port}, device={target_device}")
        except Exception as e:
            logger.error(f"Cascade catalog query send failed: {e}")
            self._cascade_call_ids.discard(call_id)

    async def send_keepalive(self, platform: ParentPlatform) -> None:
        """No-op: PlatformService._keepalive_loop manages keepalive automatically."""
        pass

    async def send_catalog_response(self, platform: ParentPlatform, sn: str, channels: list, from_tag: str) -> None:
        """Delegate: send catalog response via PlatformService."""
        svc = _get_svc()
        if svc:
            await svc.send_catalog_response(platform, sn, channels, from_tag)

    async def send_catalog_notify(self, platform: ParentPlatform, channels: list, status: str = "ON") -> None:
        """Delegate: send catalog NOTIFY via PlatformService."""
        svc = _get_svc()
        if svc:
            await svc.send_catalog_notify(platform, channels, status)

    async def send_invite_response(
        self,
        platform: ParentPlatform,
        request: SipMessage,
        sdp_ip: str,
        sdp_port: int,
        ssrc: str,
        is_tcp: bool = False,
    ) -> None:
        """Delegate: send INVITE 200 OK via PlatformService."""
        svc = _get_svc()
        if svc:
            await svc.send_invite_response(platform, request, sdp_ip, sdp_port, ssrc, is_tcp)

    async def send_cascade_playback_invite(
        self,
        platform: ParentPlatform,
        channel_id: str,
        start_time: str,
        end_time: str,
        sdp_ip: str,
        sdp_port: int,
        ssrc: str,
        is_tcp: bool = False,
    ) -> str | None:
        """Send a playback INVITE to a cascade (lower) platform.

        Args:
            platform: The lower platform to send INVITE to
            channel_id: Channel GB ID on the lower platform
            start_time: Start time in ISO format (e.g., "2024-01-01T00:00:00")
            end_time: End time in ISO format
            sdp_ip: Local media IP for SDP
            sdp_port: Local media port for SDP
            ssrc: SSRC for the playback session
            is_tcp: Whether to use TCP for media transport

        Returns:
            Call-ID of the INVITE, or None on failure
        """
        from app.core.config import settings, sip_host_for_contact, sip_via_host, sip_from_to_host
        from app.sip.send import send_sip_bytes

        # 级联回放SSRC通过ssrc_manager分配，防止冲突
        _allocated_ssrc = False
        if not ssrc:
            try:
                from app.sip.ssrc_manager import ssrc_manager as _ssrc_mgr
                ssrc = await _ssrc_mgr.allocate(is_playback=True)
                _allocated_ssrc = True
                if not ssrc:
                    logger.error("Cascade playback INVITE: SSRC allocation exhausted")
                    return None
            except Exception as _ssrc_err:
                logger.error(f"Cascade playback INVITE: SSRC allocation failed: {_ssrc_err}")
                return None

        server_gb_id = platform.server_gb_id
        server_ip = platform.server_ip
        server_port = platform.server_port or 5060
        proto = "TCP" if is_tcp else "UDP"
        transport_proto = platform.transport or "UDP"
        # platform.transport 可能是字符串而非传输层对象，需要从 SipServer 获取实际传输对象
        actual_transport = None
        try:
            from app.sip.server import sip_server as _sip_server_ref
            if _sip_server_ref:
                actual_transport = _sip_server_ref.get_transport(server_ip, server_port, str(transport_proto).upper())
        except Exception as _transport_err:
            logger.warning(f"Cascade playback: failed to get transport from sip_server: {_transport_err}")
        if actual_transport is None:
            logger.error(f"Cannot get transport object for cascade INVITE to {server_ip}:{server_port}, proto={transport_proto}")
            return None

        # Build SDP for playback
        from app.sip.sdp import build_sdp
        media_profile = "TCP/RTP/AVP" if is_tcp else "RTP/AVP"
        setup_val = "passive" if is_tcp else None
        time_range = f"{start_time} {end_time}"
        sdp_body = build_sdp(
            origin_id=channel_id,
            session_name="Playback",
            connection_ip=sdp_ip,
            media_port=sdp_port,
            media_profile=media_profile,
            direction="recvonly",
            ssrc=ssrc,
            setup=setup_val,
            time_range=time_range,
        )  # build_sdp要求全部关键字参数，之前使用位置参数导致TypeError

        req = SipMessage()
        req.method = "INVITE"
        req.uri = f"sip:{channel_id}@{server_ip}:{server_port}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(8)}"
        from_tag = secrets.token_hex(8)  # FIX [2026-07-17 P1]: 64位随机性（RFC 3261 §19.3）
        call_id = f"cascade_pb_{secrets.token_hex(8)}@{sip_via_host()}"

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={from_tag}"
        req.headers["To"] = f"<sip:{channel_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = call_id
        # FIX [2026-07-17 P1]: CSeq 单调递增（RFC 3261 §22.2）
        from app.sip.commander import _next_cseq as _cascade_next_cseq
        req.headers["CSeq"] = f"{_cascade_next_cseq()} INVITE"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Content-Type"] = "application/sdp"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.body = sdp_body if isinstance(sdp_body, str) else sdp_body.decode("utf-8")

        try:
            await send_sip_bytes(proto, actual_transport, (server_ip, server_port), req.to_bytes())
            logger.info(f"Cascade playback INVITE sent to {server_gb_id}, channel={channel_id}, call_id={call_id}")
            return call_id
        except Exception as e:
            logger.error(f"Cascade playback INVITE send failed: {e}")
            # 发送失败时释放已分配的SSRC
            if _allocated_ssrc and ssrc:
                try:
                    from app.sip.ssrc_manager import ssrc_manager as _ssrc_mgr
                    await _ssrc_mgr.release(ssrc)
                except Exception as _ssrc_err:
                    logger.warning(f"Cascade playback: failed to release SSRC {ssrc}: {_ssrc_err}")
            return None

    async def send_alarm_notify(
        self,
        platform: ParentPlatform,
        device_id: str,
        channel_id: str,
        alarm_type: str,
        priority: str,
        description: str,
        alarm_time_iso: str,
    ) -> None:
        """Delegate: send alarm notify via PlatformService."""
        svc = _get_svc()
        if svc:
            await svc.send_alarm_notify(platform, device_id, channel_id, alarm_type, priority, description, alarm_time_iso)


cascade_commander = SipCascadeCommander()
