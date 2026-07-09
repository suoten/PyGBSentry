"""GB28181 设备控制（DeviceControl）命令实现。

封装 GB28181 ``CmdType=DeviceControl`` 系列指令的 SIP MESSAGE 构造与发送，
包括：
- 录像控制（RecordCmd: Record / StopRecord）
- 布防控制（GuardCmd: SetGuard / ResetGuard）
- 报警复位（AlarmCmd: ResetAlarm）
- 重启（TeleBoot）
- 复位（Reset）
- 位置查询（Position）
- IFrame 请求（IFameCmd）
- 拉框放大/缩小（DragZoomIn / DragZoomOut）
- 配置上传/下载/设置（ConfigUpload / ConfigDownload / ConfigSet）
- 预置位查询（PresetQuery）

SIP 消息构造风格与 ``commander.py`` / ``ptz.py`` 保持一致：
- ``MESSAGE`` 方法，``Content-Type: Application/MANSCDP+xml``
- ``Via`` 带 ``rport`` 与 ``branch=z9hG4bK...``
- ``From`` / ``To`` 使用 ``settings.SIP_ID`` / 设备域

``DeviceControl(sip_server)`` 构造，``device_control`` 为模块级单例（初始为 None，
在 ``main.py`` lifespan 中被赋值为 ``DeviceControl(sip_server)``）。
"""
from __future__ import annotations

import secrets
from typing import Any, Optional
from xml.sax.saxutils import escape as _xml_escape

from loguru import logger

from app.core.config import settings, sip_host_for_contact
from app.sip.send import send_sip_bytes
from app.sip.sn import next_sn

# SipMessage 延迟导入：app.sip.message 由并行 agent 提供，避免其在 WIP 状态下
# 导致本模块顶层导入失败（NEVER raise from a top-level import）。
SipMessage = None  # type: ignore[assignment]


def _get_sip_message_cls():
    """惰性获取 SipMessage 类（首次调用时导入 app.sip.message）。"""
    global SipMessage
    if SipMessage is None:
        from app.sip.message import SipMessage as _SipMessage
        SipMessage = _SipMessage
    return SipMessage


def _attach_trace_header(req) -> None:
    call_id = (req.get_header("Call-ID") or "").strip()
    if call_id:
        req.headers["X-Trace-ID"] = call_id


def _build_device_control_message(
    device_id: str,
    channel_id: str,
    transport_info: tuple,
    inner_xml: str,
    call_suffix: str,
) -> tuple[Any, tuple, str, Any, Any]:
    """构造 DeviceControl MESSAGE 请求。

    ``inner_xml`` 为 ``<CmdType>`` 之后的子元素 XML 片段（不含 CmdType/SN/DeviceID）。
    返回 ``(req, addr, proto, transport, sn)``。
    """
    addr, proto, transport = transport_info
    sn = next_sn()
    _SipMessage = _get_sip_message_cls()
    xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(channel_id)}</DeviceID>
{inner_xml}
</Control>
"""
    req = _SipMessage()
    req.method = "MESSAGE"
    req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
    req.version = "SIP/2.0"
    req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch=z9hG4bK{secrets.token_hex(5)}{call_suffix}"
    req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={secrets.token_hex(4)}{call_suffix}"
    req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
    req.headers["Call-ID"] = f"{secrets.token_hex(8)}_{call_suffix}@{sip_host_for_contact()}"
    req.headers["CSeq"] = "1 MESSAGE"
    req.headers["Content-Type"] = "Application/MANSCDP+xml"
    req.headers["Max-Forwards"] = "70"
    req.headers["User-Agent"] = settings.PROJECT_NAME
    _attach_trace_header(req)
    req.body = xml_body
    return req, addr, proto, transport, sn


async def _send_device_control(
    device_id: str,
    channel_id: str,
    transport_info: tuple,
    inner_xml: str,
    call_suffix: str,
    log_label: str,
) -> int:
    """构造并发送 DeviceControl MESSAGE，返回 SN。"""
    req, addr, proto, transport, sn = _build_device_control_message(
        device_id, channel_id, transport_info, inner_xml, call_suffix
    )
    data = req.to_bytes()
    try:
        await send_sip_bytes(proto, transport, addr, data)
    except Exception as e:
        logger.warning(f"Failed to send DeviceControl {log_label} to {channel_id}: {e}")
        return sn
    logger.info(f"Sent DeviceControl {log_label} to {channel_id} (device={device_id}), sn={sn}")
    return sn


def _device_id_from_asset(asset: Any) -> str:
    """从 asset 对象提取 device_id（gb_id）。"""
    return str(getattr(asset, "gb_id", "") or "")


class DeviceControl:
    """GB28181 设备控制命令发送器。

    ``sip_server`` 参数保留以兼容 lifespan 初始化（``DeviceControl(sip_server)``），
    实际 SIP 发送通过 ``app.sip.send.send_sip_bytes`` 完成。
    """

    def __init__(self, sip_server: Any = None) -> None:
        self.sip_server = sip_server

    # ------------------------------------------------------------------
    # 录像控制（RecordCmd）
    # ------------------------------------------------------------------

    async def send_record_control(
        self, asset: Any, channel_id: str, transport_info: tuple, action: str = "Record"
    ) -> int:
        """设备端录像控制。``action``: ``Record``（开始）/ ``StopRecord``（停止）。"""
        device_id = _device_id_from_asset(asset)
        inner = f"<RecordCmd>{_xml_escape(action)}</RecordCmd>"
        return await _send_device_control(
            device_id, channel_id, transport_info, inner, "rc", f"RecordCmd({action})"
        )

    # ------------------------------------------------------------------
    # 布防控制（GuardCmd）
    # ------------------------------------------------------------------

    async def send_guard(
        self, asset: Any, channel_id: str, transport_info: tuple, action: str = "SetGuard"
    ) -> int:
        """布防/撤防控制。``action``: ``SetGuard`` / ``ResetGuard``。"""
        device_id = _device_id_from_asset(asset)
        inner = f"<GuardCmd>{_xml_escape(action)}</GuardCmd>"
        return await _send_device_control(
            device_id, channel_id, transport_info, inner, "guard", f"GuardCmd({action})"
        )

    # ------------------------------------------------------------------
    # 报警复位（AlarmCmd）
    # ------------------------------------------------------------------

    async def send_alarm_reset(
        self, asset: Any, channel_id: str, transport_info: tuple
    ) -> int:
        """报警复位（AlarmCmd=ResetAlarm）。"""
        device_id = _device_id_from_asset(asset)
        inner = "<AlarmCmd>ResetAlarm</AlarmCmd>"
        return await _send_device_control(
            device_id, channel_id, transport_info, inner, "alarm", "AlarmCmd(ResetAlarm)"
        )

    # ------------------------------------------------------------------
    # 重启 / 复位（TeleBoot / Reset）
    # ------------------------------------------------------------------

    async def send_reboot(
        self, asset: Any, channel_id: str, transport_info: tuple
    ) -> int:
        """设备重启（TeleBoot=Reboot）。"""
        device_id = _device_id_from_asset(asset)
        inner = "<TeleBoot>Reboot</TeleBoot>"
        return await _send_device_control(
            device_id, channel_id, transport_info, inner, "reboot", "TeleBoot(Reboot)"
        )

    async def send_reset(
        self, asset: Any, channel_id: str, transport_info: tuple
    ) -> int:
        """设备复位（Reset）。"""
        device_id = _device_id_from_asset(asset)
        inner = "<Reset>reset</Reset>"
        return await _send_device_control(
            device_id, channel_id, transport_info, inner, "reset", "Reset"
        )

    # ------------------------------------------------------------------
    # 位置查询（Position）
    # ------------------------------------------------------------------

    async def send_position_query(
        self, asset: Any, channel_id: str, transport_info: tuple
    ) -> int:
        """主动请求设备上报一次移动位置（Position）。"""
        device_id = _device_id_from_asset(asset)
        inner = "<Position>1</Position>"
        return await _send_device_control(
            device_id, channel_id, transport_info, inner, "pos", "Position"
        )

    # ------------------------------------------------------------------
    # IFrame 请求（IFameCmd）
    # ------------------------------------------------------------------

    async def send_iframe_request(
        self, asset: Any, channel_id: str, transport_info: tuple
    ) -> int:
        """请求设备立即发送一个 I 帧（IFameCmd）。"""
        device_id = _device_id_from_asset(asset)
        inner = "<IFameCmd>1</IFameCmd>"
        return await _send_device_control(
            device_id, channel_id, transport_info, inner, "iframe", "IFameCmd"
        )

    # ------------------------------------------------------------------
    # 拉框放大/缩小（DragZoomIn / DragZoomOut）
    # ------------------------------------------------------------------

    async def send_dragzoom(
        self,
        asset: Any,
        channel_id: str,
        transport_info: tuple,
        direction: str = "in",
        *,
        top_left_x: int = 0,
        top_left_y: int = 0,
        bottom_right_x: int = 0,
        bottom_right_y: int = 0,
        length: int = 1920,
        width: int = 1080,
    ) -> int:
        """拉框放大/缩小（DragZoomIn / DragZoomOut）。

        ``direction``: ``in``（放大）/ ``out``（缩小）。
        其余参数为拉框坐标与画面尺寸。
        """
        device_id = _device_id_from_asset(asset)
        tag = "DragZoomIn" if str(direction).lower() == "in" else "DragZoomOut"
        inner = (
            f"<{tag}>\n"
            f"<Length>{int(length)}</Length>\n"
            f"<Width>{int(width)}</Width>\n"
            f"<TopLeftX>{int(top_left_x)}</TopLeftX>\n"
            f"<TopLeftY>{int(top_left_y)}</TopLeftY>\n"
            f"<BottomRightX>{int(bottom_right_x)}</BottomRightX>\n"
            f"<BottomRightY>{int(bottom_right_y)}</BottomRightY>\n"
            f"</{tag}>"
        )
        return await _send_device_control(
            device_id, channel_id, transport_info, inner, "dz", tag
        )

    # ------------------------------------------------------------------
    # 配置相关（ConfigUpload / ConfigDownload / ConfigSet / PresetQuery）
    # ------------------------------------------------------------------
    # 这些方法被 commander.py 通过 lazy import 桥接调用，使用 device_id 关键字参数。

    async def send_config_upload(
        self,
        device_id: str,
        channel_id: str,
        transport_info: tuple,
        config_type: str = "BasicParam",
        config_data: str = "",
    ) -> Optional[str]:
        """设备配置上传（DeviceControl + ConfigUpload）。

        请求设备将指定类型的配置上报给平台。
        """
        inner = (
            f"<ConfigUpload>\n"
            f"<ConfigType>{_xml_escape(config_type)}</ConfigType>\n"
            f"</ConfigUpload>"
        )
        sn = await _send_device_control(
            device_id, channel_id, transport_info, inner, "cup", f"ConfigUpload({config_type})"
        )
        return str(sn)

    async def send_config_download(
        self,
        device_id: str,
        channel_id: str,
        transport_info: tuple,
        config_type: str = "BasicParam",
    ) -> Optional[str]:
        """设备配置下载查询（DeviceControl + ConfigDownload）。"""
        inner = (
            f"<ConfigDownload>\n"
            f"<ConfigType>{_xml_escape(config_type)}</ConfigType>\n"
            f"</ConfigDownload>"
        )
        sn = await _send_device_control(
            device_id, channel_id, transport_info, inner, "cdn", f"ConfigDownload({config_type})"
        )
        return str(sn)

    async def send_config_set(
        self,
        device_id: str,
        channel_id: str,
        transport_info: tuple,
        config_type: str = "BasicParam",
        config_params: Optional[dict[str, Any]] = None,
    ) -> Optional[str]:
        """设备配置设置（DeviceControl + ConfigSet）。

        ``config_params`` 为键值对，序列化为 ``<Param><K>v</K>...</Param>`` 子元素。
        """
        params_xml = ""
        if config_params and isinstance(config_params, dict):
            for k, v in config_params.items():
                params_xml += f"<{_xml_escape(str(k))}>{_xml_escape(str(v))}</{_xml_escape(str(k))}>\n"
        inner = (
            f"<ConfigSet>\n"
            f"<ConfigType>{_xml_escape(config_type)}</ConfigType>\n"
            f"{params_xml}"
            f"</ConfigSet>"
        )
        sn = await _send_device_control(
            device_id, channel_id, transport_info, inner, "cset", f"ConfigSet({config_type})"
        )
        return str(sn)

    async def send_preset_query(
        self,
        device_id: str,
        channel_id: str,
        transport_info: tuple,
    ) -> Optional[str]:
        """预置位查询（DeviceControl + PresetQuery）。"""
        inner = "<PresetQuery>1</PresetQuery>"
        sn = await _send_device_control(
            device_id, channel_id, transport_info, inner, "pq", "PresetQuery"
        )
        return str(sn)


# 模块级单例：初始为 None，在 main.py lifespan 中赋值为 DeviceControl(sip_server)
device_control: Optional[DeviceControl] = None
