from app.sip.message import SipMessage
from app.db.session import AsyncSessionLocal
from app.models.stream_session import StreamSession
from app.models.asset_stream_policy import AssetStreamPolicy
from app.models.asset_stream_health import AssetStreamHealth
from app.models.media_node import MediaNode
from sqlalchemy import select
import app.sip.invite as invite_module
from loguru import logger  # 统一使用 loguru 替代 logging
import asyncio
import contextlib
import random
import secrets
import string
import re
from app.sip.send import send_sip_bytes
from app.core.config import settings
from typing import Optional

# GB2 3xx重定向自动跟随 — 重定向计数器，防止循环
_REDIRECT_COUNTS: dict[str, int] = {}
_REDIRECT_COUNTS_MAX = 5000




async def _wait_stream_registered(
    node_host: str,
    node_http_port: int,
    secret: str,
    app: str,
    stream: str,
    timeout: float = 5.0,
    on_found: Optional[callable] = None,
) -> tuple[bool, dict]:
    """
    等待 ZLM 流注册（最多 timeout 秒）。
    返回 (found, media_item)。即使流注册在不同 app（如 rtp）下也能找到。
    找到流后调用 on_found(app, stream, media_item)。
    """
    # 延迟导入避免循环依赖
    from app.api.v1.endpoints.stream import _probe_zlm_stream
    _loop = asyncio.get_running_loop()
    start = _loop.time()
    interval = 0.2
    while (_loop.time() - start) < timeout:
        probe_ok, stream_found, media_item = await _probe_zlm_stream(
            node_host, node_http_port, secret, app, stream, extra_apps=["rtp", "live", "playback"]
        )
        if probe_ok and stream_found and media_item:
            registered_app = str(media_item.get("app") or app)
            registered_stream = str(media_item.get("stream") or stream)
            logger.info(
                f"[StreamWait] Stream registered: app={registered_app} stream={registered_stream} "
                f"on node {node_host}:{node_http_port} (elapsed={(_loop.time()-start)*1000:.0f}ms)"
            )
            if on_found:
                try:
                    await asyncio.shield(on_found(registered_app, registered_stream, media_item))
                except Exception as e:
                    logger.warning(f"[StreamWait] on_found callback failed: {e}")
            return True, media_item
        await asyncio.sleep(interval)
        interval = min(interval + 0.1, 0.5)
    return False, {}

def _extract_tag(header_value: str | None) -> str:
    if not header_value:
        return ""
    for part in header_value.split(";"):
        item = part.strip()
        if item.lower().startswith("tag="):
            return item.split("=", 1)[1].strip()
    return ""

def _normalize_mode(protocol: str | None) -> str:
    value = (protocol or "UDP").strip().upper().replace("-", "_")
    if value not in {"UDP", "TCP_PASSIVE", "TCP_ACTIVE"}:
        return "UDP"
    return value


async def _update_learning_state_failure(session, mode: str) -> None:
    try:
        import json
        import time as _time
        from app.models.system_setting import SystemSetting

        setting_result = await session.execute(
            select(SystemSetting).where(SystemSetting.setting_key == "gb28181.bootstrap_learning_state")
        )
        setting = setting_result.scalars().first()
        learning_state = {}
        if setting and setting.setting_value:
            try:
                learning_state = json.loads(setting.setting_value) or {}
            except Exception:
                learning_state = {}
        profiles = learning_state.setdefault("profiles", {})
        profile = profiles.setdefault("default_profile", {"updated_at": 0})
        mode_stat = profile.setdefault(mode, {"s": 0, "f": 0})
        mode_stat["f"] = min(9999, int(mode_stat.get("f", 0) or 0) + 1)
        profile["updated_at"] = int(_time.time())
        serialized = json.dumps(learning_state, ensure_ascii=False, separators=(",", ":"))
        if len(serialized) <= 1900:
            if not setting:
                setting = SystemSetting(setting_key="gb28181.bootstrap_learning_state", setting_value=serialized)
                session.add(setting)
            else:
                setting.setting_value = serialized
    except Exception as e:
        logger.warning(f"Error: {e}")


async def _record_stream_health(session, stream_session: StreamSession, status_code: int):
    result = await session.execute(select(AssetStreamHealth).where(AssetStreamHealth.asset_id == stream_session.asset_id))
    health = result.scalars().first()
    if not health:
        health = AssetStreamHealth(asset_id=stream_session.asset_id)
        session.add(health)
    
    is_success = (status_code < 300) and (status_code != 202)
    
    health.last_status_code = status_code
    health.last_mode = _normalize_mode(stream_session.protocol)
    health.success_total = int(getattr(health, "success_total", 0) or 0)
    health.fail_total = int(getattr(health, "fail_total", 0) or 0)
    health.consecutive_failures = int(getattr(health, "consecutive_failures", 0) or 0)
    health.auto_switch_count = int(getattr(health, "auto_switch_count", 0) or 0)
    
    if is_success:
        health.success_total += 1
        health.consecutive_failures = 0
        health.last_mode = _normalize_mode(stream_session.protocol)  # C-23 成功时也更新last_mode
        return
        
    health.fail_total += 1
    health.consecutive_failures += 1
    
    if stream_session.app != "live":
        return

    # 模式特定的失败追踪：从 SystemSetting 中读取 learning_state
    # 这样可以与 stream.py 中的 _record_runtime_play_health 保持一致
    current_mode = _normalize_mode(stream_session.protocol)
    await _update_learning_state_failure(session, current_mode)

    if health.consecutive_failures < 2:
        return
        
    policy_result = await session.execute(select(AssetStreamPolicy).where(AssetStreamPolicy.asset_id == stream_session.asset_id))
    policy = policy_result.scalars().first()

    # 从 learning_state 获取各模式的失败次数
    from app.models.system_setting import SystemSetting
    setting_result = await session.execute(
        select(SystemSetting).where(SystemSetting.setting_key == "gb28181.bootstrap_learning_state")
    )
    setting = setting_result.scalars().first()
    learning_state = {}
    if setting and setting.setting_value:
        import json as _json
        try:
            learning_state = _json.loads(setting.setting_value) or {}
        except Exception:
            learning_state = {}
    profiles = learning_state.get("profiles", {}) if isinstance(learning_state, dict) else {}
    default_profile = profiles.get("default_profile") or profiles.get("no_asset_profile") or {}
    
    def _get_failures(mode_key: str) -> int:
        m = default_profile.get(mode_key) if isinstance(default_profile, dict) else {}
        return int(m.get("f", 0)) if isinstance(m, dict) else 0

    if not policy:
        # 新设备优先尝试 UDP
        policy = AssetStreamPolicy(asset_id=stream_session.asset_id, stream_mode="UDP")
        session.add(policy)
        logger.warning(f"[Auto Fallback] Created policy UDP for asset {stream_session.asset_id} due to {health.consecutive_failures} failures.")
    else:
        current_policy_mode = str(getattr(policy, "stream_mode", "") or "").strip().upper()
        if current_policy_mode == "UDP" and _get_failures("UDP") >= 2:
            policy.stream_mode = "TCP_PASSIVE"
            health.auto_switch_count += 1
            health.consecutive_failures = 0
            logger.warning(f"[Auto Fallback] Switched policy to TCP_PASSIVE for asset {stream_session.asset_id} due to UDP failures.")
        elif current_policy_mode == "TCP_PASSIVE" and _get_failures("TCP_PASSIVE") >= 2:
            policy.stream_mode = "TCP_ACTIVE"
            health.auto_switch_count += 1
            health.consecutive_failures = 0
            logger.warning(f"[Auto Fallback] Switched policy to TCP_ACTIVE for asset {stream_session.asset_id} due to TCP_PASSIVE failures.")
        elif current_policy_mode == "TCP_ACTIVE" and _get_failures("TCP_ACTIVE") >= 2:
            policy.stream_mode = "UDP"
            health.auto_switch_count += 1
            health.consecutive_failures = 0
            logger.warning(f"[Auto Fallback] Switched policy to UDP for asset {stream_session.asset_id} due to TCP_ACTIVE failures.")
        elif current_policy_mode in {"AUTO", "GLOBAL", ""}:
            # AUTO 模式：按顺序尝试
            if _get_failures("UDP") >= 2:
                policy.stream_mode = "TCP_PASSIVE"
            elif _get_failures("TCP_PASSIVE") >= 2:
                policy.stream_mode = "TCP_ACTIVE"
            elif _get_failures("TCP_ACTIVE") >= 2:
                policy.stream_mode = "UDP"
            if policy.stream_mode != current_policy_mode and policy.stream_mode:
                health.auto_switch_count += 1
                health.consecutive_failures = 0
                logger.warning(f"[Auto Fallback] AUTO policy switched to {policy.stream_mode} for asset {stream_session.asset_id}.")

async def handle_invite_response(message: SipMessage, addr: tuple, proto: str, transport):
    status_code = int(message.status_code or 0)
    call_id = message.get_header("Call-ID") or ""

    if call_id in invite_module.invite_state.cascade_call_ids:
        return

    if 200 <= status_code < 300:
        logger.info(f"Received 200 OK for INVITE from {message.from_header}")
    elif 300 <= status_code < 400:
        # W-01 RFC 3261要求对3xx最终响应发送ACK
        try:
            _ack_req = SipMessage()
            _ack_req.method = "ACK"
            _ack_req.uri = f"sip:{addr[0]}:{addr[1]}"
            _ack_req.version = "SIP/2.0"
            _ack_req.headers["Via"] = message.get_header("Via") or ""
            _ack_req.headers["From"] = message.get_header("From") or ""
            _ack_req.headers["To"] = message.get_header("To") or ""
            _ack_req.headers["Call-ID"] = call_id
            _cseq_h = message.get_header("CSeq") or "1 INVITE"
            _ack_req.headers["CSeq"] = f"{_cseq_h.split(' ')[0]} ACK"
            _ack_req.headers["Max-Forwards"] = "70"
            await send_sip_bytes(proto, transport, addr, _ack_req.to_bytes())
        except Exception as _ack_err:
            logger.debug(f"ACK for 3xx failed: {_ack_err}")
        # GB2 3xx重定向自动跟随 — RFC 3261 Section 8.1.3.4
        contact_header = message.get_header("Contact") or message.get_header("m") or ""
        if contact_header:
            # Extract URI from Contact header
            contact_uri = re.search(r'<([^>]+)>', contact_header)
            if contact_uri:
                new_uri = contact_uri.group(1)
                logger.info(f"3xx redirect: following Contact {new_uri} for Call-ID={call_id}")
                # Reconstruct INVITE with new Request-URI and resend
                # (up to 5 redirects max to prevent loops)
                _redirect_count = _REDIRECT_COUNTS.get(call_id, 0) + 1
                if _redirect_count <= 5:
                    _REDIRECT_COUNTS[call_id] = _redirect_count
                    if len(_REDIRECT_COUNTS) > _REDIRECT_COUNTS_MAX:
                        _keys = list(_REDIRECT_COUNTS.keys())
                        for k in _keys[:len(_REDIRECT_COUNTS) - _REDIRECT_COUNTS_MAX + 100]:
                            _REDIRECT_COUNTS.pop(k, None)
                    try:
                        from app.core.config import settings, sip_host_for_contact
                        new_branch = f"z9hG4bK{secrets.token_hex(8)}"
                        cseq_header = message.get_header("CSeq") or "1 INVITE"
                        cseq_parts = cseq_header.split()
                        # CSeq序列号非数字时ValueError崩溃，改为安全解析
                        try:
                            cseq_num = str(int(cseq_parts[0]) + 1) if cseq_parts else "2"
                        except (ValueError, IndexError):
                            cseq_num = "2"
                        from_h = message.get_header("From") or ""
                        to_h = message.get_header("To") or ""
                        # Remove to-tag for new INVITE
                        to_h_no_tag = re.sub(r';tag=[^;>]+', '', to_h)

                        redirect_req = SipMessage()
                        redirect_req.method = "INVITE"
                        redirect_req.uri = new_uri
                        redirect_req.version = "SIP/2.0"
                        redirect_req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={new_branch}"
                        redirect_req.headers["From"] = from_h
                        redirect_req.headers["To"] = to_h_no_tag
                        redirect_req.headers["Call-ID"] = call_id
                        redirect_req.headers["CSeq"] = f"{cseq_num} INVITE"
                        redirect_req.headers["Max-Forwards"] = "70"
                        redirect_req.headers["User-Agent"] = getattr(settings, "PROJECT_NAME", "PyGBSentry")
                        redirect_req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
                        # C-04 3xx重定向INVITE携带原始SDP，而非空body
                        _pending_entry = invite_module.invite_state.invite_pending.get(call_id)
                        original_sdp = _pending_entry[1].get("original_sdp", "") if _pending_entry else ""
                        redirect_req.body = original_sdp

                        # S-02 3xx重定向INVITE发送到Contact URI目标地址(RFC 3261 §8.1.3.4)，而非原响应方地址
                        _redirect_addr = addr  # fallback to original addr
                        try:
                            _uri_match = re.match(r'sip:([^@]+@)?([^:;>]+)(?::(\d+))?', str(new_uri or ""))
                            if _uri_match:
                                _redirect_host = _uri_match.group(2)
                                _redirect_port = int(_uri_match.group(3) or 5060)
                                _redirect_addr = (_redirect_host, _redirect_port)
                        except (ValueError, TypeError, IndexError):
                            pass
                        await send_sip_bytes(proto, transport, _redirect_addr, redirect_req.to_bytes())
                        # S-07 3xx重定向后取消原watchdog并注册新watchdog，
                        # 否则原watchdog超时会清理pending条目和资源，导致重定向INVITE无响应
                        try:
                            invite_module.cancel_invite_watchdog(call_id)
                            _pending_entry = invite_module.invite_state.invite_pending.get(call_id)
                            if _pending_entry:
                                _on_timeout_cb = _pending_entry[1].get("watchdog_on_timeout")
                                if _on_timeout_cb:
                                    from app.sip.watchdog import start_watchdog
                                    _invite_timeout = int(getattr(settings, "SIP_INVITE_RESPONSE_TIMEOUT_SECONDS", 20) or 20)
                                    start_watchdog(key=f"invite:{call_id}", timeout_seconds=_invite_timeout, on_timeout=_on_timeout_cb)
                        except Exception as _wd_err:
                            logger.warning(f"3xx redirect: failed to reset watchdog for Call-ID={call_id}: {_wd_err}")
                        logger.info(f"3xx redirect: resent INVITE to {new_uri} for Call-ID={call_id} (redirect #{_redirect_count})")
                        return
                    except Exception as e:
                        logger.warning(f"3xx redirect resend failed: {e}")
                else:
                    logger.warning(f"3xx redirect loop detected (>{_redirect_count} redirects) for Call-ID={call_id}")
                    # W-07 重定向循环检测后清理_REDIRECT_COUNTS，防止内存泄漏
                    _REDIRECT_COUNTS.pop(call_id, None)
        # If redirect fails, fall through to failure handling
        logger.warning(f"3xx redirect failed or no Contact header for Call-ID={call_id}")
    elif 400 <= status_code < 700:
        logger.info(f"Received {status_code} for INVITE from {message.from_header}")

    if status_code < 200:
        call_id_val = message.get_header("Call-ID")
        to_tag = _extract_tag(message.get_header("To"))
        if call_id_val:
            invite_module.on_invite_provisional(call_id_val, status_code, message.reason_phrase or "")
        if call_id_val and to_tag:
            from_tag = _extract_tag(message.get_header("From"))
            if from_tag:
                try:
                    from app.sip.dialog_manager import dialog_manager, DialogState
                    dialog = await dialog_manager.get_dialog(call_id_val, from_tag)
                    if dialog and dialog.state == DialogState.EARLY:
                        async with dialog._lock:  # W-06-01 1xx修改dialog属性加锁，防止与confirm_dialog/terminate_dialog竞态
                            if dialog.state == DialogState.EARLY:  # 重新检查，锁获取期间状态可能已变更
                                dialog.to_tag = to_tag
                                dialog.state = DialogState.EARLY
                except Exception as e:
                    logger.debug(f"Exception: {e}")

        # PRACK可靠1xx支持（RFC 3262）— 对带Require:100rel的1xx响应发送PRACK
        require_header = message.get_header("Require") or ""
        rseq_header = message.get_header("RSeq") or ""
        if "100rel" in require_header.lower() and rseq_header and call_id_val:
            try:
                from app.core.config import settings, sip_host_for_contact
                cseq_header = message.get_header("CSeq") or "1 INVITE"
                cseq_num = cseq_header.split()[0] if cseq_header else "1"
                branch = f"z9hG4bK{secrets.token_hex(6)}"
                from_tag_val = _extract_tag(message.get_header("From")) or ""
                to_tag_val = _extract_tag(message.get_header("To")) or ""

                prack = SipMessage()
                prack.method = "PRACK"
                prack.uri = message.get_header("Contact") or f"sip:{addr[0]}:{addr[1]}"
                if "<" in prack.uri:
                    try:
                        prack.uri = prack.uri.split("<")[1].split(">")[0]
                    except (IndexError, ValueError):
                        pass
                prack.version = "SIP/2.0"
                prack.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
                from_h = message.get_header("From") or ""
                prack.headers["From"] = from_h
                to_h = message.get_header("To") or ""
                prack.headers["To"] = to_h
                prack.headers["Call-ID"] = call_id_val
                prack.headers["CSeq"] = f"{cseq_num} PRACK"
                prack.headers["RAck"] = f"{rseq_header} {cseq_header}"
                prack.headers["Max-Forwards"] = "70"
                prack.headers["User-Agent"] = settings.PROJECT_NAME
                prack.body = ""

                await send_sip_bytes(proto, transport, addr, prack.to_bytes())
                logger.info(f"[PRACK] Sent PRACK for {status_code} response, Call-ID={call_id_val}, RSeq={rseq_header}")
            except Exception as prack_err:
                logger.warning(f"[PRACK] Failed to send PRACK: {prack_err}")
        return

    # C-21 对讲INVITE的ACK由on_talk_200_ok统一发送，此处跳过避免双重ACK
    _is_talk_invite = False
    try:
        from app.sip import talk as _talk_mod
        if call_id in _talk_mod._talk_pending:
            _is_talk_invite = True
    except Exception as _talk_check_err:
        # 对讲模块导入失败时记录日志，否则双重ACK问题无法诊断
        logger.debug(f"Failed to check talk pending for {call_id}: {_talk_check_err}")

    if not _is_talk_invite:
        req = SipMessage()
        req.method = "ACK"
        contact = message.get_header("Contact")
        if contact and "sip:" in contact:
            try:
                uri = contact.split("<")[1].split(">")[0] if "<" in contact else contact  # Contact头解析IndexError防护
            except (IndexError, ValueError):
                uri = contact.strip("<>").split(";")[0] if contact else f"sip:{addr[0]}:{addr[1]}"
            req.uri = uri
        else:
            to_h = message.get_header("To") or ""
            if "<" in to_h:
                req.uri = to_h.split("<")[1].split(">")[0]
            else:
                from_h = message.get_header("From") or ""
                if "sip:" in from_h:
                    req.uri = "sip:" + from_h.split("sip:")[1].split(">")[0].split(";")[0]
                else:
                    req.uri = f"sip:{addr[0]}:{addr[1]}"

        req.version = "SIP/2.0"

        via_header = message.get_header("Via") or ""
        if 200 <= status_code < 300:
            via_parts = via_header.split(";")
            new_via_parts = []
            for part in via_parts:
                p = part.strip()
                if p.lower().startswith("branch="):
                    new_branch = f"z9hG4bK{secrets.token_hex(8)}"
                    new_via_parts.append(f"branch={new_branch}")
                else:
                    new_via_parts.append(part)
            if not any(p.lower().startswith("branch=") for p in new_via_parts):
                new_branch = f"z9hG4bK{secrets.token_hex(8)}"
                new_via_parts.append(f"branch={new_branch}")
            req.headers["Via"] = ";".join(new_via_parts)
        else:
            req.headers["Via"] = via_header

        req.headers["From"] = message.get_header("From") or ""  # str|None → str
        req.headers["To"] = message.get_header("To") or ""  # str|None → str
        req.headers["Call-ID"] = call_id
        cseq_header = message.get_header("CSeq") or "1 INVITE"
        cseq_num = cseq_header.split(" ")[0]
        req.headers["CSeq"] = f"{cseq_num} ACK"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = getattr(settings, "PROJECT_NAME", "PyGBSentry")

        data = req.to_bytes()

        try:
            from app.sip import transactions as sip_transactions
            tx_manager = getattr(sip_transactions, "client_tx_manager", None) or getattr(sip_transactions, "tx_manager", None)
            if tx_manager is None:
                raise RuntimeError("sip_client_tx_manager_unavailable")

            # W-06 2xx ACK直接发送(RFC 3261 §13.2.2.4)，不通过事务管理器，
            # 避免创建永远不会被resolve的无用事务浪费资源
            if 200 <= status_code < 300:
                await send_sip_bytes(proto, transport, addr, data)
            else:
                await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Error sending ACK via tx_manager: {e}, falling back to direct send")
            await send_sip_bytes(proto, transport, addr, data)

    to_tag = _extract_tag(message.get_header("To"))
    if call_id:
        _REDIRECT_COUNTS.pop(call_id, None)  # C-16 INVITE最终完成时清理重定向计数器，防止内存泄漏
        try:
            invite_module.cancel_invite_watchdog(call_id)
        except Exception as e:
            logger.warning(f"Error: {e}")
        try:
            from app.sip.watchdog import cancel_stream_switch_watchdog
            cancel_stream_switch_watchdog(call_id)
        except Exception as e:
            logger.warning(f"Error: {e}")
        async with invite_module.invite_state.stream_switch_lock:
            invite_module.invite_state.stream_switch_pending.pop(call_id, None)
            invite_module.invite_state.stream_switch_rollback_depth.pop(call_id, None)
            invite_module.invite_state.stream_switch_rollback_depth_timestamps.pop(call_id, None)
            invite_module.invite_state.stream_switch_pending_timestamps.pop(call_id, None)

        # 广播INVITE 200 OK响应处理 — 清理pending并记录广播会话状态
        pending_entry = invite_module.invite_state.invite_pending.get(call_id)  # C-18 用get而非pop，让on_invite_response负责最终消费
        if pending_entry:
            _, pending_result = pending_entry  # C-08 _INVITE_PENDING值是tuple[Event,dict]，需解包后取dict
            if pending_result.get("type") == "broadcast":
                if status_code == 200:
                    logger.info(f"[Broadcast] Device accepted broadcast INVITE, call_id={call_id}")
                elif status_code >= 300:
                    logger.warning(f"[Broadcast] Device rejected broadcast INVITE with {status_code}, call_id={call_id}")
                    # 广播被拒绝，清理StreamSession
                    try:
                        async with AsyncSessionLocal() as session:
                            ss = (await session.execute(select(StreamSession).where(StreamSession.call_id == call_id))).scalars().first()
                            if ss:
                                await session.delete(ss)
                                await session.commit()
                    except Exception as e:
                        logger.warning(f"[Broadcast] Failed to cleanup rejected broadcast session: {e}")

        invite_module.on_invite_response(
            call_id,
            status_code,
            message.reason_phrase or "",
            message.body or "",
            to_tag=to_tag,
            record_route=message.get_header("Record-Route"),  # GB28181协议 — 传递Record-Route头到dialog
        )
        # C-19 4xx-6xx错误处理 — 原elif分支因call_id非空为死代码，移入此分支
        if status_code >= 400:
            # C-25 清理对讲pending条目，否则_talk_pending永不释放
            try:
                from app.sip import talk as _talk_mod
                _talk_entry = _talk_mod._talk_pending.pop(call_id, None)
                if _talk_entry:
                    _, _talk_res = _talk_entry
                    _talk_sock = _talk_res.pop("socket", None)
                    if _talk_sock:
                        try:
                            _talk_sock.close()
                        except Exception as _sock_close_err:
                            logger.debug(f"Talk socket close failed: {_sock_close_err}")
                    # S-06 释放对讲SSRC，防止泄漏
                    _talk_ssrc = _talk_res.get("ssrc")
                    if _talk_ssrc:
                        try:
                            from app.sip.ssrc_manager import ssrc_manager
                            await ssrc_manager.release(str(_talk_ssrc))
                        except Exception as _ssrc_rel_err:
                            # SSRC释放失败记录日志，否则泄漏无法追踪
                            logger.warning(f"Talk SSRC release failed for {_talk_ssrc}: {_ssrc_rel_err}")
            except Exception as _talk_cleanup_err:
                logger.debug(f"Talk cleanup error for {call_id}: {_talk_cleanup_err}")
            # 流切换失败，取消超时看门狗并主动触发回退
            async with invite_module.invite_state.stream_switch_lock:
                is_stream_switch = call_id in invite_module.invite_state.stream_switch_pending
                saved_target_type = invite_module.invite_state.stream_switch_pending.get(call_id)
                invite_module.invite_state.stream_switch_pending.pop(call_id, None)
                invite_module.invite_state.stream_switch_pending_timestamps.pop(call_id, None)
            try:
                from app.sip.watchdog import cancel_stream_switch_watchdog
                cancel_stream_switch_watchdog(call_id)
            except Exception as e:
                logger.warning(f"Error: {e}")
            # 流切换失败时主动触发回退
            if is_stream_switch and invite_module.sip_invite:
                try:
                    inviter = invite_module.sip_invite
                    if inviter:
                        await inviter._do_stream_switch_rollback(call_id, saved_target_type=saved_target_type)
                except Exception as rollback_err:
                    logger.warning(f"[Stream Switch] Rollback after failure failed for {call_id}: {rollback_err}")
                return
            # 协议降级重试
            if invite_module.sip_invite:
                inviter = invite_module.sip_invite
                retried = await inviter.retry_invite_with_fallback(call_id) if inviter else False
                if not retried:
                    try:
                        async with AsyncSessionLocal() as session:
                            result = await session.execute(select(StreamSession).where(StreamSession.call_id == call_id))
                            stream_session = result.scalars().first()
                            if stream_session:
                                old_lease_id = getattr(stream_session, "_pending_old_lease_id", None)
                                if old_lease_id:
                                    try:
                                        from app.core.media_nodes_db import release_lease
                                        async with AsyncSessionLocal() as lease_session:
                                            await release_lease(lease_session, old_lease_id)
                                            await lease_session.commit()
                                    except Exception as lease_err:
                                        logger.warning(f"Failed to release old lease after INVITE 4xx: {lease_err}")
                                await _record_stream_health(session, stream_session, message.status_code)
                                from app.services.stream_session_service import finalize_stream_session
                                await finalize_stream_session(session, stream_session, reason=f"invite_failed_{int(message.status_code or 0)}")
                                await session.commit()
                    except Exception as e:
                        logger.error(f"invite_failed cleanup DB error for {call_id}: {e}")
            return
        stream_session = None
        if call_id:
            try:
                async with AsyncSessionLocal() as session:
                    result = await session.execute(select(StreamSession).where(StreamSession.call_id == call_id))
                    stream_session = result.scalars().first()
                    if stream_session:
                        # SSRC Waiter 已在 _send_invite_common 中提前注册，此处不再重复注册（避免重置 Redis TTL）
                        if to_tag:
                            stream_session.to_tag = to_tag
                    
                        sdp_body = message.body or ""
                        sdp_lower = sdp_body.lower()
                        is_tcp_active_reply = (
                            ("tcp/rtp/avp" in sdp_lower) and ("a=setup:active" in sdp_lower)
                        )
                        if is_tcp_active_reply and stream_session.protocol != "TCP-ACTIVE":
                            stream_session.protocol = "TCP-ACTIVE"
                        dev_ssrc = ""
                        dev_port = 0
                        dev_ip = ""
                        dev_pt = ""
                        if sdp_body:
                            try:
                                m_ssrc = re.search(r'y=(\d+)', sdp_body)
                                m_port = re.search(r'm=(?:video|audio) (\d+)', sdp_body)
                                m_ip = re.search(r'c=IN IP4 (\d+\.\d+\.\d+\.\d+)', sdp_body)
                                m_pt = re.search(r'm=(?:video|audio) \d+ [^\s]+ (\d+)', sdp_body)
                            
                                dev_ssrc = m_ssrc.group(1).strip() if m_ssrc else ""
                                dev_port = int(m_port.group(1).strip()) if m_port else 0
                                dev_ip = m_ip.group(1).strip() if m_ip else ""
                                dev_pt = m_pt.group(1).strip() if m_pt else ""
                            except Exception:
                                dev_ssrc = ""
                                dev_port = 0
                                dev_ip = ""
                                dev_pt = ""
                            
                        # NAT Traversal: Send Dummy RTP Packet
                        if stream_session.protocol == "UDP" and dev_ip and dev_port > 0:
                            try:
                                # C-29 NAT打洞使用线程池避免阻塞事件循环
                                def _send_dummy_rtp():
                                    import socket as _socket
                                    _sock = None
                                    try:
                                        _sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
                                        _sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
                                        _sock.settimeout(0.5)
                                        _pt_val = int(dev_pt) if dev_pt.isdigit() else 96
                                        _dummy = bytes([0x80, _pt_val, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                                        _sock.sendto(_dummy, (dev_ip, dev_port))
                                        logger.info(f"Sent Dummy RTP packet to {dev_ip}:{dev_port} (PT={_pt_val}) for NAT traversal")
                                    finally:
                                        if _sock:
                                            _sock.close()
                                await asyncio.get_running_loop().run_in_executor(None, _send_dummy_rtp)
                            except Exception as e:
                                logger.warning(f"Failed to send Dummy RTP packet: {e}")
                            
                        if dev_ssrc and dev_ssrc != stream_session.ssrc:
                            logger.info(f"Device modified SSRC in 200 OK: {stream_session.ssrc} -> {dev_ssrc}")
                            old_ssrc = stream_session.ssrc
                            stream_session.ssrc = dev_ssrc
                            # W-03 先分配新SSRC再释放旧SSRC，消除竞态窗口
                            try:
                                from app.sip.ssrc_manager import ssrc_manager
                                # R-07 allocate_specific_ssrc失败时回滚DB引用并跳过释放旧SSRC
                                if ssrc_manager and dev_ssrc:
                                    _is_playback = str(dev_ssrc).startswith("1")
                                    allocated = await ssrc_manager.allocate_specific_ssrc(dev_ssrc, is_playback=_is_playback)  # C-07
                                    if not allocated:
                                        stream_session.ssrc = old_ssrc
                                        logger.warning(f"allocate_specific_ssrc failed for {dev_ssrc}, keeping old SSRC {old_ssrc}")
                                    else:
                                        if ssrc_manager and old_ssrc:
                                            await ssrc_manager.release_ssrc(old_ssrc)  # C-07 补充await，否则协程不执行致SSRC泄漏
                            except Exception as ssrc_err:
                                logger.warning(f"Failed to update SSRC manager during device SSRC change: {ssrc_err}")
                            # We must update ZLM RTP server SSRC regardless of TCP-ACTIVE or UDP
                            try:
                                from app.services.zlm_rtp_server_service import update_rtp_server_ssrc
                                # removed redundant inner import of MediaNode, using module-level import
                                if stream_session.media_server_id:
                                    node_result = await session.execute(select(MediaNode).where(MediaNode.id == stream_session.media_server_id))
                                    node = node_result.scalars().first()
                                    if node:
                                        # Need to pass integer string to prevent ZLM octal parsing bug
                                        try:
                                            from app.services.zlm_rtp_server_service import update_rtp_server_ssrc
                                            await update_rtp_server_ssrc(
                                                host=getattr(node, 'stream_ip', None) or getattr(node, 'public_ip', None) or getattr(settings, 'STREAM_PUBLIC_HOST', '') or node.ip,
                                                http_port=node.http_port or 0,
                                                secret=node.secret or settings.MEDIA_SERVER_SECRET or "",
                                                app=stream_session.app,
                                                stream_id=stream_session.stream,
                                                ssrc=str(int(dev_ssrc))
                                            )
                                        except Exception as zlm_err:
                                            logger.error(f"Failed to call update_rtp_server_ssrc API: {zlm_err}")
                            except Exception as inner_e:
                                logger.error(f"Failed to update ZLM SSRC on 200 OK: {inner_e}")

                        if stream_session.protocol == "TCP-ACTIVE" and sdp_body:
                            try:
                                if dev_port > 0:
                                    logger.info(f"[TCP-ACTIVE] Device requires TCP connection to {addr[0]}:{dev_port}")
                                    _tcp_connect_retries = 3
                                    _tcp_connect_delay = 0.5
                                    last_error = None
                                    for attempt in range(_tcp_connect_retries):
                                        try:
                                            from app.services.zlm_rtp_server_service import connect_rtp_server
                                            # removed redundant inner import of MediaNode
                                            if stream_session.media_server_id:
                                                node_result = await session.execute(select(MediaNode).where(MediaNode.id == stream_session.media_server_id))
                                                node = node_result.scalars().first()
                                                if node:
                                                    await connect_rtp_server(
                                                        host=getattr(node, 'stream_ip', None) or getattr(node, 'public_ip', None) or getattr(settings, 'STREAM_PUBLIC_HOST', '') or node.ip,
                                                        http_port=node.http_port or 0,
                                                        secret=node.secret or settings.MEDIA_SERVER_SECRET or "",
                                                        dst_url=dev_ip or addr[0],
                                                        dst_port=dev_port,
                                                        app=stream_session.app,
                                                        stream_id=stream_session.stream
                                                    )
                                                    logger.info(f"[TCP-ACTIVE] Successfully connected ZLM to device at {addr[0]}:{dev_port} (attempt {attempt + 1})")
                                                    last_error = None
                                                    break
                                        except Exception as inner_e:
                                            last_error = inner_e
                                            logger.warning(f"[TCP-ACTIVE] Failed to connect ZLM to device (attempt {attempt + 1}/{_tcp_connect_retries}): {inner_e}")
                                            if attempt < _tcp_connect_retries - 1:
                                                await asyncio.sleep(_tcp_connect_delay * (attempt + 1))
                                    if last_error:
                                        logger.error(f"[TCP-ACTIVE] All {_tcp_connect_retries} connection attempts failed for {addr[0]}:{dev_port}, cleaning up session")
                                        await _record_stream_health(session, stream_session, 503)
                                        try:
                                            from app.services.stream_session_service import finalize_stream_session
                                            await finalize_stream_session(session, stream_session, reason="tcp_active_connect_failed")
                                            await session.commit()
                                            return
                                        except Exception as fin_err:
                                            with contextlib.suppress(Exception):
                                                await session.rollback()
                                            logger.warning(f"[TCP-ACTIVE] Failed to finalize session after connect failure: {fin_err}")
                                        return
                            except Exception as e:
                                logger.error(f"[TCP-ACTIVE] Failed to parse 200 OK SDP: {e}")
                    
                        await _record_stream_health(session, stream_session, message.status_code)
                        await session.commit()

                        old_lease_id = getattr(stream_session, "_pending_old_lease_id", None)
                        if old_lease_id:
                            try:
                                from app.core.media_nodes_db import release_lease
                                async with AsyncSessionLocal() as lease_session:
                                    await release_lease(lease_session, old_lease_id)
                                    await lease_session.commit()
                            except Exception as lease_err:
                                logger.warning(f"Failed to release old lease after Re-INVITE 200 OK: {lease_err}")
                            try:
                                del stream_session._pending_old_lease_id
                            except Exception as e:
                                logger.debug(f"Exception: {e}")

                        # 异步等待 ZLM 流注册：200 OK 收到后设备开始推流，
                        # ZLM 需要几秒将流从 rtp app 迁移/注册到目标 app（live/playback）。
                        # 如果不等就直接返回，前端轮询 getMediaList 时流可能还没就绪。
                        if stream_session.media_server_id and stream_session.app and stream_session.stream:
                            node_result = await session.execute(select(MediaNode).where(MediaNode.id == stream_session.media_server_id))
                            node = node_result.scalars().first()
                            if node and node.ip and node.http_port:
                                _session_id = str(stream_session.id or "")
                                _original_app = str(stream_session.app or "live")
                                _original_stream = str(stream_session.stream or "")
                                _node_host = str(getattr(node, 'stream_ip', None) or getattr(node, 'public_ip', None) or node.ip)
                                _node_http_port = int(node.http_port or 0)
                                _secret = str(node.secret or "") or str(settings.MEDIA_SERVER_SECRET or "")

                                async def _on_stream_found(registered_app: str, registered_stream: str, media_item: dict):
                                    try:
                                        async with AsyncSessionLocal() as update_session:
                                            ss = (await update_session.execute(
                                                select(StreamSession).where(StreamSession.id == _session_id)
                                            )).scalars().first()
                                            if ss:
                                                old_app = str(ss.app or "")
                                                old_stream = str(ss.stream or "")
                                                ss.app = registered_app
                                                ss.stream = registered_stream
                                                await update_session.commit()
                                                logger.info(
                                                    f"[StreamWait] Updated StreamSession {_session_id}: "
                                                    f"app {old_app}->{registered_app}, stream {old_stream}->{registered_stream}"
                                                )
                                    except Exception as e:
                                        logger.warning(f"[StreamWait] Failed to update StreamSession {_session_id}: {e}")  # update_session possibly unbound in except

                                asyncio.create_task(_wait_stream_registered(
                                    _node_host,
                                    _node_http_port,
                                    _secret,
                                    _original_app,
                                    _original_stream,
                                    timeout=6.0,
                                    on_found=_on_stream_found,
                                ))
                # 对讲 INVITE 的 200 OK：无 StreamSession 时若为待办对讲会话，解析 SDP 供对讲端发送 RTP
                if not stream_session:
                    try:
                        from app.sip import talk as talk_module
                        if call_id in talk_module._talk_pending:
                            # on_talk_200_ok 已改为 async，需要 await
                            await talk_module.on_talk_200_ok(call_id, message.body or "", to_tag=to_tag)
                    except Exception as e:
                        logger.debug(f"Talk 200 OK handling: {e}")
            except Exception as e:
                logger.error(f"handle_invite_response DB error for call_id={call_id}: {e}")

        logger.info("Sent ACK")
        
    elif 100 <= message.status_code < 200:
        call_id = message.get_header("Call-ID")
        if call_id:
            invite_module.on_invite_provisional(call_id, message.status_code, message.reason_phrase or "")
        logger.debug(f"INVITE provisional response: {message.status_code} {message.reason_phrase}")
        
    elif message.status_code >= 400:
        logger.error(f"INVITE failed with {message.status_code} {message.reason_phrase}")
        call_id = message.get_header("Call-ID")
        if call_id:
            _REDIRECT_COUNTS.pop(call_id, None)  # C-16 INVITE失败时也清理重定向计数器
            # 对讲INVITE 4xx-6xx时清理_talk_pending和释放SSRC，否则资源泄漏
            try:
                from app.sip import talk as _talk_mod_err
                _talk_entry_err = _talk_mod_err._talk_pending.pop(call_id, None)
                if _talk_entry_err:
                    _, _talk_res_err = _talk_entry_err
                    _talk_sock_err = _talk_res_err.pop("socket", None)
                    if _talk_sock_err:
                        try:
                            _talk_sock_err.close()
                        except Exception:
                            pass
                    _talk_ssrc_err = _talk_res_err.get("ssrc")
                    if _talk_ssrc_err:
                        try:
                            from app.sip.ssrc_manager import ssrc_manager
                            await ssrc_manager.release(str(_talk_ssrc_err))
                        except Exception as _ssrc_err:
                            logger.warning(f"Talk SSRC release failed on INVITE error for {_talk_ssrc_err}: {_ssrc_err}")
            except Exception as _talk_err_cleanup:
                logger.debug(f"Talk cleanup on INVITE error for {call_id}: {_talk_err_cleanup}")
            try:
                invite_module.cancel_invite_watchdog(call_id)
            except Exception as e:
                logger.warning(f"Error: {e}")
            try:
                from app.sip.invite import unregister_ssrc_waiter
                async with AsyncSessionLocal() as ss:
                    ss_result = await ss.execute(select(StreamSession).where(StreamSession.call_id == call_id))
                    ss_obj = ss_result.scalars().first()
                    if ss_obj and ss_obj.ssrc:
                        await unregister_ssrc_waiter(str(ss_obj.ssrc))
            except Exception as e:
                logger.debug(f"Exception: {e}")
            # 流切换失败，取消超时看门狗并主动触发回退
            async with invite_module.invite_state.stream_switch_lock:
                is_stream_switch = call_id in invite_module.invite_state.stream_switch_pending
                saved_target_type = invite_module.invite_state.stream_switch_pending.get(call_id)
            try:
                from app.sip.watchdog import cancel_stream_switch_watchdog
                cancel_stream_switch_watchdog(call_id)
            except Exception as e:
                logger.warning(f"Error: {e}")
            async with invite_module.invite_state.stream_switch_lock:
                invite_module.invite_state.stream_switch_pending.pop(call_id, None)
                invite_module.invite_state.stream_switch_pending_timestamps.pop(call_id, None)
            # 通知等待 INVITE 响应的协程（错误响应）
            invite_module.on_invite_response(
                call_id,
                message.status_code,
                message.reason_phrase or "",
                message.body or "",
                record_route=message.get_header("Record-Route"),  # GB28181协议 — 传递Record-Route头到dialog
            )
            # 流切换失败时主动触发回退（不做协议降级重试）
            if is_stream_switch and invite_module.sip_invite:
                try:
                    inviter = invite_module.sip_invite
                    if inviter:  # pyright None narrowing
                        await inviter._do_stream_switch_rollback(call_id, saved_target_type=saved_target_type)
                except Exception as rollback_err:
                    logger.warning(f"[Stream Switch] Rollback after failure failed for {call_id}: {rollback_err}")
                return
        if call_id and invite_module.sip_invite:
            retried = False  # retried possibly unbound
            inviter = invite_module.sip_invite
            if inviter:
                retried = await inviter.retry_invite_with_fallback(call_id)
            if not retried:
                try:
                    async with AsyncSessionLocal() as session:
                        result = await session.execute(select(StreamSession).where(StreamSession.call_id == call_id))
                        stream_session = result.scalars().first()
                        if stream_session:
                            old_lease_id = getattr(stream_session, "_pending_old_lease_id", None)
                            if old_lease_id:
                                try:
                                    from app.core.media_nodes_db import release_lease
                                    async with AsyncSessionLocal() as lease_session:
                                        await release_lease(lease_session, old_lease_id)
                                        await lease_session.commit()
                                except Exception as lease_err:
                                    logger.warning(f"Failed to release old lease after INVITE 4xx: {lease_err}")
                            await _record_stream_health(session, stream_session, message.status_code)
                            from app.services.stream_session_service import finalize_stream_session
                            await finalize_stream_session(session, stream_session, reason=f"invite_failed_{int(message.status_code or 0)}")  # 移除内部 loguru import，统一使用模块级 logger
                            await session.commit()
                except Exception as e:
                    logger.error(f"invite_failed cleanup DB error for {call_id}: {e}")