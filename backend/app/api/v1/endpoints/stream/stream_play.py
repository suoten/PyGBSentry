"""播放/停止相关端点。"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, status, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_db, AsyncSessionLocal
from app.core.config import settings
from app.core.media_nodes import get_node_by_id
from app.core.media_nodes_db import get_db_media_node_by_id
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.stream_session import StreamSession
from app.models.user import User
from app.api import deps
import app.sip.invite as sip_invite_module
from app.sip.server import sip_server
from app.core.plugin_manager import plugin_manager
from app.services.stream_session_service import release_stream_session, finalize_stream_session
from typing import Any
from types import SimpleNamespace
import contextlib
import logging
import time
import asyncio

from ._shared import (
    logger,
    _PlayIdempotencyGuard,
    _stream_audit,
    _record_play_trace,
    _read_play_trace,
    _record_play_failure,
    _normalize_signal_proto,
    _media_mode_label,
    _build_signal_targets,
    _build_live_session_stream_key,
    _build_stream_match_hints,
    _wait_zlm_stream_ready,
    _probe_stream_across_nodes,
    _probe_zlm_stream,
    _record_runtime_play_health,
    _resolve_media_mode_candidates,
    _get_gb28181_play_config,
    _ssrc_policy_chain,
    _INVITE_ENDPOINT_HINTS,
    _PLAY_STATUS_RECENT_FAILURE,
    _do_warmup_flv,
    _get_max_concurrent_streams,
)
from ._response import (
    _build_full_play_response,
    _map_play_stream_error,
    _play_http_exception,
)

# W-12 markers for port exhaustion detection (SIP module may output either form)
_PORT_EXHAUSTED_MARKERS = ("media_port_exhausted", "收流端口不足")

router = APIRouter()


class StopStreamRequest(BaseModel):
    app: str | None = None
    stream: str | None = None
    device_id: str | None = None
    channel_id: str | None = None


@router.get("/errors/catalog")
async def stream_error_catalog(
    current_user: User = Depends(deps.get_current_active_user),
):
    items = [
        {"reason_code": "media_secret_invalid", "http_status": 502, "retryable": False, "message": "Media node auth config missing"},  # i18n
        {"reason_code": "media_node_unavailable", "http_status": 503, "retryable": True, "message": "No available media node to receive video stream"},  # i18n
        {"reason_code": "media_node_unreachable", "http_status": 503, "retryable": True, "message": "Media node connection failed"},  # i18n
        {"reason_code": "stream_not_ready", "http_status": 504, "retryable": True, "message": "Stream not ready"},  # i18n
        {"reason_code": "sip_service_unavailable", "http_status": 503, "retryable": True, "message": "SIP service not ready"},
        {"reason_code": "device_transport_unavailable", "http_status": 503, "retryable": True, "message": "Device signaling transport unavailable"},
        {"reason_code": "asset_or_channel_not_found", "http_status": 404, "retryable": False, "message": "Device or channel not found"},
        {"reason_code": "max_concurrent_streams", "http_status": 429, "retryable": True, "message": "Concurrent stream limit reached"},  # i18n
        {"reason_code": "play_request_failed", "http_status": 502, "retryable": True, "message": "Stream invite request failed"},  # i18n
    ]
    data = []
    for item in items:
        normalized_reason = str(item["reason_code"]).strip().lower().replace(" ", "_").replace("-", "_")
        error_code = f"GB_STREAM_{normalized_reason.upper()}"
        data.append(
            {
                "error_code": error_code,
                "reason_code": item["reason_code"],
                "http_status": int(item["http_status"]),
                "retryable": bool(item["retryable"]),
                "message": str(item["message"]),
                "domain": "stream",
                "version": "2026-04",
            }
        )
    return {"domain": "stream", "version": "2026-04", "items": data}


async def _async_invite_wait_with_retry(
    stream_session_id: str,
    stream_type: str,
    max_attempts: int,
    interval_seconds: float,
):
    async with AsyncSessionLocal() as db:
        _record_play_trace(stream_session_id, "async_task_started", {"stream_type": str(stream_type or "main")})
        cfg = await _get_gb28181_play_config(db)
        chain = _ssrc_policy_chain(cfg)
        if not bool(cfg.get("ssrc_retry_on_not_ready", True)):
            chain = chain[:1]
        ss = (await db.execute(select(StreamSession).where(StreamSession.id == stream_session_id))).scalars().first()
        if not ss:
            return
        asset = (await db.execute(select(Asset).where(Asset.id == ss.asset_id))).scalars().first()
        resource = (await db.execute(select(Resource).where(Resource.id == ss.resource_id))).scalars().first()
        media_mode_candidates = await _resolve_media_mode_candidates(db, getattr(ss, "asset_id", None), asset=asset)
        if not asset or not resource or not asset.ip_addr:
            _record_play_trace(stream_session_id, "async_task_failed", {"reason": "invalid_asset_or_resource"})
            _record_play_failure(
                stream_session_id,
                {"reason": "invalid_asset_or_resource", "retryable": True},
            )
            await finalize_stream_session(db, ss, reason="media_stream_not_ready")
            await db.commit()
            return
        asset_invite = SimpleNamespace(
            id=str(getattr(asset, "id", "") or ""),
            gb_id=str(getattr(asset, "gb_id", "") or ""),
            ip_addr=str(getattr(asset, "ip_addr", "") or ""),
            port=int(getattr(asset, "port", 0) or 0),
            transport=str(getattr(asset, "transport", "") or "UDP"),
            tenant_id=str(getattr(asset, "tenant_id", "") or "default"),
        )
        resource_invite = SimpleNamespace(
            id=str(getattr(resource, "id", "") or ""),
            gb_id=str(getattr(resource, "gb_id", "") or ""),
        )
        if not sip_invite_module.sip_invite:
            _record_play_trace(stream_session_id, "async_task_failed", {"reason": "sip_service_unavailable"})
            _record_play_failure(
                stream_session_id,
                {"reason": "sip_service_unavailable", "retryable": True},
            )
            await finalize_stream_session(db, ss, reason="media_stream_not_ready")
            await db.commit()
            return
        targets = await _build_signal_targets(db, asset)
        if not targets:
            _record_play_trace(stream_session_id, "async_task_failed", {"reason": "device_transport_unavailable"})
            _record_play_failure(
                stream_session_id,
                {"reason": "device_transport_unavailable", "retryable": True},
            )
            await finalize_stream_session(db, ss, reason="media_stream_not_ready")
            await db.commit()
            return
        final_reason = "media_stream_not_ready"
        for idx, policy in enumerate(chain):
            _record_play_trace(
                stream_session_id,
                "invite_policy_attempt",
                {"policy": str(policy or "adaptive"), "attempt_index": int(idx + 1), "total": int(len(chain))},
            )
            result = None
            had_transport = False
            invite_errors: list[str] = []
            for target_ip, target_port, target_proto_raw in targets:
                transport_proto = _normalize_signal_proto(target_proto_raw)
                transport = sip_server.get_transport(target_ip, target_port, transport_proto)
                if transport is None and transport_proto == "TCP":
                    transport_proto = "UDP"
                    transport = sip_server.get_transport(target_ip, target_port, transport_proto)
                if transport is None:
                    invite_errors.append(f"{target_ip}:{int(target_port)}/{transport_proto}:transport_unavailable")
                    continue
                had_transport = True
                for media_mode in media_mode_candidates:
                    try:
                        result = await sip_invite_module.sip_invite.send_invite(
                            asset_invite,
                            resource_invite,
                            ((target_ip, target_port), transport_proto, transport),
                            stream_type=stream_type,
                            zlm_ssrc_check=(policy == "strict"),
                            media_mode_override=media_mode,
                            reuse_stream_session_id=stream_session_id,
                        )
                        _record_play_trace(
                            stream_session_id,
                            "invite_sent",
                            {
                                "policy": str(policy or "adaptive"),
                                "target": f"{target_ip}:{int(target_port)}/{transport_proto}",
                                "media_mode": _media_mode_label(media_mode),
                            },
                        )
                        break
                    except Exception as exc:
                        invite_errors.append(
                            f"{target_ip}:{int(target_port)}/{transport_proto}:{_media_mode_label(media_mode)}:{str(exc)[:180]}"
                        )
                        continue
                if result:
                    break
            if not result:
                if not had_transport:
                    final_reason = "device_transport_unavailable"
                elif any(marker in seg for marker in _PORT_EXHAUSTED_MARKERS for seg in invite_errors):
                    final_reason = "media_port_exhausted"
                elif invite_errors:
                    final_reason = "invite_send_failed"
                else:
                    final_reason = "media_stream_not_ready"
                _record_play_trace(
                    stream_session_id,
                    "invite_failed",
                    {
                        "policy": str(policy or "adaptive"),
                        "reason": final_reason,
                        "errors": invite_errors[:20],
                    },
                )
                _record_play_failure(
                    stream_session_id,
                    {
                        "reason": final_reason,
                        "retryable": True,
                        "policy": str(policy or "adaptive"),
                        "signal_targets_tried": [f"{ip}:{port}/{proto}" for ip, port, proto in (targets or [])],
                        "media_modes_tried": [_media_mode_label(m) for m in media_mode_candidates],
                        "errors": invite_errors[:20],
                    },
                )
                if idx < (len(chain) - 1):
                    await asyncio.sleep(0.8)
                continue
            node_id = result.get("node_id")
            app_name = result.get("app") or "live"
            stream_id = result.get("stream") or str(resource.gb_id or "")
            stream_hints = _build_stream_match_hints(stream_id, str(result.get("ssrc") or getattr(ss, "ssrc", "") or ""))
            db_node = await get_db_media_node_by_id(db, node_id) if node_id else None
            node = None if db_node else get_node_by_id(node_id)
            if db_node:
                host, http_port, secret = db_node.host, int(db_node.http_port or 0), str(db_node.secret or "")
            elif node:
                host, http_port, secret = node.get("host") or "", int(node.get("http_port") or 0), str(node.get("secret") or "")
            else:
                break
            zlm_probe_ok, zlm_stream_ready, media_item, probe_detail = await _wait_zlm_stream_ready(
                host,
                http_port,
                secret,
                app_name,
                stream_id,
                max_attempts=max_attempts,
                interval_seconds=interval_seconds,
                stream_hints=stream_hints,
                extra_apps=["rtp"],
                ssrc=str(result.get("ssrc") or ""),
            )
            if not zlm_stream_ready:
                cluster_ready, cluster_node, cluster_media_item, cluster_detail = await _probe_stream_across_nodes(
                    db,
                    app=app_name,
                    stream=stream_id,
                    stream_hints=stream_hints,
                    preferred_node_id=node_id,
                    extra_apps=["rtp"],
                )
                if cluster_ready:
                    zlm_probe_ok = True
                    zlm_stream_ready = True
                    media_item = cluster_media_item
                    probe_detail = {**(probe_detail or {}), **(cluster_detail or {})}
                    host = str(cluster_node.get("host") or host)
                    http_port = int(cluster_node.get("http_port") or http_port)
                    secret = str(cluster_node.get("secret") or secret)
                    node_id = str(cluster_node.get("id") or node_id or "")
                    if ss:
                        ss.media_server_id = node_id or ss.media_server_id
                else:
                    probe_detail = {**(probe_detail or {}), **(cluster_detail or {})}
            if zlm_probe_ok and zlm_stream_ready:
                _record_play_trace(
                    stream_session_id,
                    "stream_ready",
                    {"app": str((media_item or {}).get("app") or app_name), "stream": str((media_item or {}).get("stream") or stream_id)},
                )
                await _record_runtime_play_health(
                    db,
                    asset_id=getattr(asset, "id", None),
                    mode=str(result.get("media_protocol") or ""),
                    success=True,
                    status_code=200,
                )
                await db.commit()
                matched_app = str((media_item or {}).get("app") or app_name or "live")
                matched_stream = str((media_item or {}).get("stream") or stream_id or str(resource.gb_id or ""))
                _INVITE_ENDPOINT_HINTS[str(asset.gb_id or "").strip()] = {
                    "ip": target_ip,
                    "port": int(target_port),
                    "proto": str(transport_proto or "UDP"),
                }
                if ss:
                    ss.app = matched_app
                    ss.stream = matched_stream
                if (asset.ip_addr != target_ip) or int(asset.port or 0) != int(target_port or 0):
                    asset.ip_addr = target_ip
                    asset.port = int(target_port)
                    asset.transport = transport_proto
                await db.commit()

                if matched_app == "live":
                    _snap_asset_gb_id = str(asset.gb_id)
                    _snap_resource_gb_id = str(resource.gb_id)
                    def _take_background_snapshot():
                        time.sleep(3.5)
                        from app.api.v1.endpoints.devices.devices_control import _try_snap_async, _snapshot_cache_file  # C-09 _try_snap_sync不存在，改用_try_snap_async
                        st_hint = "main" if "sub" not in matched_stream.lower() else "sub"
                        cache_file = _snapshot_cache_file(_snap_asset_gb_id, _snap_resource_gb_id, st_hint)
                        try:  # C-09 在后台线程中创建新事件循环调用async函数
                            loop = asyncio.new_event_loop()
                            loop.run_until_complete(_try_snap_async(host, http_port, secret, matched_app, matched_stream, cache_file, 2))
                        finally:
                            loop.close()
                    
                    _snap_future = asyncio.get_running_loop().run_in_executor(None, _take_background_snapshot)

                    def _on_snap_done(t):
                        try:
                            t.result()
                        except Exception as _snap_err:
                            logger.warning(f"[PlayStream] Background snapshot failed: {_snap_err}")

                    _snap_future.add_done_callback(_on_snap_done)

                # 预热 HTTP-FLV 端点
                _flv_suffix = "" if matched_app == "rtp" else ".live"
                _flv_url = f"http://{host}:{http_port}/{matched_app}/{matched_stream}{_flv_suffix}.flv"
                _flv_log = logger
                await _do_warmup_flv(_flv_url, _flv_log, matched_app, matched_stream)

                return
            _record_play_trace(
                stream_session_id,
                "stream_not_ready",
                {"policy": str(policy or "adaptive"), "probe": probe_detail or {}, "node_host": host, "node_http_port": http_port},
            )
            final_reason = "media_stream_not_ready"
            _record_play_failure(
                stream_session_id,
                {
                    "reason": "media_stream_not_ready",
                    "retryable": True,
                    "signal_targets_tried": [f"{ip}:{port}/{proto}" for ip, port, proto in (targets or [])],
                    "media_modes_tried": [_media_mode_label(m) for m in media_mode_candidates],
                    "probe": probe_detail or {},
                    "node_host": host,
                    "node_http_port": http_port,
                    "app": app_name,
                    "stream": stream_id,
                },
            )
            await _record_runtime_play_health(
                db,
                asset_id=getattr(asset, "id", None),
                mode=str(result.get("media_protocol") or ""),
                success=False,
                status_code=503,
            )
            await db.commit()
            if idx < (len(chain) - 1):
                await asyncio.sleep(0.8)
        ss = (await db.execute(select(StreamSession).where(StreamSession.id == stream_session_id))).scalars().first()
        if ss:
            _record_play_trace(stream_session_id, "session_finalized", {"reason": final_reason})
            if getattr(ss, "to_tag", None):
                await release_stream_session(db, ss, reason=final_reason)
            else:
                await finalize_stream_session(db, ss, reason=final_reason)
            await db.commit()

@router.get("/play_status/{session_id}")
async def get_play_status(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    return await _play_status_inner(session_id, db, current_user)


class PlayStatusRequest(BaseModel):  # S-28 用Pydantic模型替代裸dict，防止非字符串session_id导致AttributeError
    session_id: str


@router.post("/play_status")  # W-10 新增POST端点，session_id从请求体获取，防止URL泄露
async def post_play_status(
    body: PlayStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    session_id = body.session_id.strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    return await _play_status_inner(session_id, db, current_user)


async def _play_status_inner(session_id: str, db: AsyncSession, current_user: User):
    _record_play_trace(session_id, "status_polled")
    default_interval = float(getattr(settings, "STREAM_WAIT_READY_INTERVAL", 0.25) or 0.25)
    default_attempts = int(getattr(settings, "STREAM_WAIT_READY_MAX_ATTEMPTS", 40) or 40)
    chain_len = 2 if bool(getattr(settings, "GB28181_SSRC_RETRY_ON_NOT_READY", True)) else 1
    next_poll_ms = max(400, min(1200, int(max(default_interval, 0.2) * 1000)))
    timeout_recommend_ms = max(20000, int(default_attempts * max(default_interval, 0.2) * 1000 * chain_len + 6000))
    session_record = (await db.execute(select(StreamSession).where(StreamSession.id == session_id, StreamSession.tenant_id == (current_user.tenant_id or "default")))).scalars().first()  # M-08 统一租户隔离模式
    if not session_record:
        failure_diag = _PLAY_STATUS_RECENT_FAILURE.get(str(session_id or "").strip()) or {}
        diagnostics = {"session_id": session_id}
        trace = _read_play_trace(session_id)
        if trace:
            diagnostics["trace"] = trace
        if failure_diag:
            diagnostics.update(failure_diag)
        reason_code = str((failure_diag or {}).get("reason") or "media_stream_not_ready")
        if reason_code == "device_transport_unavailable":
            raise _play_http_exception(
                503,
                "device_transport_unavailable",
                "Device signaling transport unavailable",
                "Please verify the device is online, registered, and SIP transport is available",  # C-28
                retryable=True,
                diagnostics=diagnostics
            )
        if reason_code == "invite_send_failed":
            raise _play_http_exception(
                503,
                "invite_send_failed",
                "Invite send failed",  # C-28 硬编码中文→英文
                "Please check device signaling connectivity, transport protocol config and node load",
                retryable=True,
                diagnostics=diagnostics
            )
        if reason_code == "media_port_exhausted":
            raise _play_http_exception(
                503,
                "media_port_exhausted",
                "Media node RTP port exhausted",  # C-28 硬编码中文→英文
                "Please scale up media node RTP port pool or release occupied sessions",
                retryable=True,
                diagnostics=diagnostics
            )
        raise _play_http_exception(
            503,
            "media_stream_not_ready",
            "Stream session ended or stream not ready (timeout)",  # C-28 硬编码中文→英文
                "Please verify the device is streaming and retry; check device codec params and media node load if needed",
            retryable=True,
            diagnostics=diagnostics
        )
    
    if not getattr(session_record, "media_server_id", None):
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "code": 202,
                "msg": "Stream starting, please continue polling",  # i18n
                "data": {
                    "status": "starting",
                    "session_id": session_id,
                    "trace": _read_play_trace(session_id),
                    "next_poll_ms": next_poll_ms,
                    "timeout_recommend_ms": timeout_recommend_ms,
                }
            }
        )

    app_name = session_record.app
    stream_id = session_record.stream
    node_id = session_record.media_server_id
    
    db_node = await get_db_media_node_by_id(db, node_id) if node_id else None
    node = None if db_node else get_node_by_id(node_id)
    selected_node = db_node or node
    
    if not selected_node:
        raise HTTPException(status_code=500, detail="Media node info missing")
        
    if db_node:
        media_host, media_port = db_node.public_host, db_node.public_http_port
        node_host, node_http_port = db_node.host, int(db_node.http_port or 0)
        is_embedded_node = bool(getattr(db_node, "is_embedded", False))
        secret = str(db_node.secret or "")
    else:
        media_host, media_port = node.get("public_host"), node.get("public_http_port")
        is_embedded_node = bool(node.get("is_embedded", False))
        node_host, node_http_port = node.get("host"), int(node.get("http_port") or 0)
        secret = str(node.get("secret") or "")
        
    max_attempts = max(8, min(20, int(default_attempts or 40)))
    zlm_probe_ok, zlm_stream_ready, media_item, probe_detail = await _wait_zlm_stream_ready(
        node_host or "",
        node_http_port or 0,
        secret,
        app_name,
        stream_id,
        max_attempts=max_attempts,
        interval_seconds=default_interval,
        stream_hints=_build_stream_match_hints(stream_id, str(getattr(session_record, "ssrc", "") or "")),
        extra_apps=["rtp"],
        ssrc=str(getattr(session_record, "ssrc", "") or ""),
    )
    
    if not zlm_stream_ready:
        stream_hints = _build_stream_match_hints(stream_id, str(getattr(session_record, "ssrc", "") or ""))
        cluster_ready, cluster_node, cluster_media_item, cluster_detail = await _probe_stream_across_nodes(
            db,
            app=app_name,
            stream=stream_id,
            stream_hints=stream_hints,
            preferred_node_id=node_id,
            extra_apps=["rtp"],
        )
        if cluster_ready:
            zlm_probe_ok = True
            zlm_stream_ready = True
            media_item = cluster_media_item
            probe_detail = {**(probe_detail or {}), **(cluster_detail or {})}
            node_id = str(cluster_node.get("id") or node_id or "")
            node_host = str(cluster_node.get("host") or node_host or "")
            node_http_port = int(cluster_node.get("http_port") or node_http_port or 0)
            media_host = str(cluster_node.get("public_host") or media_host or "")
            media_port = int(cluster_node.get("public_http_port") or media_port or 0)
            is_embedded_node = bool(cluster_node.get("is_embedded", False))
            selected_node = cluster_node
            if str(getattr(session_record, "media_server_id", "") or "") != node_id:
                session_record.media_server_id = node_id
                await db.commit()
        else:
            probe_detail = {**(probe_detail or {}), **(cluster_detail or {})}
    if not zlm_stream_ready:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "code": 202,
                "msg": "Stream not ready, please continue polling",  # C-28 中英混合→英文
                "data": {
                    "status": "waiting",
                    "zlm_probe_ok": zlm_probe_ok,
                    "zlm_stream_ready": zlm_stream_ready,
                    "probe": probe_detail,
                    "trace": _read_play_trace(session_id),
                    "next_poll_ms": next_poll_ms,
                    "timeout_recommend_ms": timeout_recommend_ms,
                }
            }
        )
    app_name = str(media_item.get("app") or app_name)
    stream_id = str(media_item.get("stream") or stream_id)
    if (session_record.app != app_name) or (session_record.stream != stream_id) or (str(getattr(session_record, "media_server_id", "") or "") != str(node_id or "")):
        session_record.app = app_name
        session_record.stream = stream_id
        if node_id:
            session_record.media_server_id = node_id
        await db.commit()

    resource = (await db.execute(select(Resource).where(Resource.id == session_record.resource_id))).scalars().first()
    
    result = {
        "call_id": session_record.call_id,
        "sdp_ip": session_record.media_ip,
        "media_port": session_record.media_port,
        "media_protocol": session_record.protocol,
        "selection_reason": "async_polled",
    }
    
    res = await _build_full_play_response(
        db=db,
        app_name=app_name,
        stream_id=stream_id,
        stream_type="main",
        selected_node=selected_node,
        media_host=media_host,
        media_port=media_port,
        node_host=node_host,
        node_http_port=node_http_port,
        is_embedded_node=is_embedded_node,
        zlm_probe_ok=zlm_probe_ok,
        zlm_stream_ready=zlm_stream_ready,
        media_item=media_item,
        result=result,
        resource=resource,
        node_id=node_id,
    )
    res["data"]["status"] = "ready"
    res["data"]["trace"] = _read_play_trace(session_id)
    return res


@router.get("/play_diagnostics/{session_id}")
async def get_play_diagnostics(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    from datetime import timezone
    session_record = (await db.execute(select(StreamSession).where(StreamSession.id == session_id, StreamSession.tenant_id == (current_user.tenant_id or "default")))).scalars().first()  # M-08 统一租户隔离模式
    failure_diag = _PLAY_STATUS_RECENT_FAILURE.get(str(session_id or "").strip()) or {}
    trace = _read_play_trace(session_id)
    payload: dict[str, Any] = {
        "session_id": session_id,
        "session_exists": bool(session_record),
        "trace": trace,
        "failure": failure_diag,
    }
    if session_record:
        payload["session"] = {
            "app": str(getattr(session_record, "app", "") or ""),
            "stream": str(getattr(session_record, "stream", "") or ""),
            "media_server_id": str(getattr(session_record, "media_server_id", "") or ""),
            "call_id": str(getattr(session_record, "call_id", "") or ""),
            "sdp_ip": str(getattr(session_record, "media_ip", "") or ""),
            "media_port": int(getattr(session_record, "media_port", 0) or 0) or None,
            "media_protocol": str(getattr(session_record, "protocol", "") or ""),
            "start_time": (
                session_record.start_time.replace(tzinfo=timezone.utc).isoformat()
                if getattr(session_record, "start_time", None) and getattr(session_record.start_time, "tzinfo", None) is None
                else (session_record.start_time.isoformat() if getattr(session_record, "start_time", None) else None)
            ),
        }
    return {"code": 200, "msg": "ok", "data": payload}


@router.post("/play/{device_id}/{channel_id}")
async def play_stream(
    device_id: str,
    channel_id: str,
    background_tasks: BackgroundTasks,
    stream_type: str = Query(
        "main",
        alias="streamType",
        description="main=主码流, sub=子码流；也支持 auto=使用通道默认偏好。streamType 为别名，stream_type 优先",
    ),
    async_mode: bool = Query(
        False,
        alias="isAsync",
        description="是否使用异步点播模式。isAsync 为别名，async_mode 优先",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    # 点播幂等性保护
    guard = _PlayIdempotencyGuard(device_id, channel_id)
    enter_ok = await guard.acquire()
    if not enter_ok:
        raise HTTPException(status_code=409, detail="VOD request for this channel is in progress, please retry later")

    try:
        req_t0 = time.perf_counter()
        stmt = select(Asset).where(Asset.gb_id == device_id)
        if not current_user.is_superuser:
            stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        result = await db.execute(stmt)
        asset = result.scalars().first()

        stmt = select(Resource).where(Resource.gb_id == channel_id)
        if not current_user.is_superuser:
            stmt = stmt.join(Asset, Asset.id == Resource.asset_id).where(Asset.tenant_id == (current_user.tenant_id or "default"))
        result = await db.execute(stmt)
        resource = result.scalars().first()

        if not asset or not resource:
            await _stream_audit(
                db,
                current_user,
                action="play_stream",
                result="failed",
                status_code=404,
                detail="asset_or_channel_not_found",
                extra_summary=f"device_id={device_id}; channel_id={channel_id}",
            )
            raise HTTPException(status_code=404, detail="Device or channel not found")

        if not asset.ip_addr:
            await _stream_audit(
                db,
                current_user,
                action="play_stream",
                result="failed",
                status_code=500,
                detail="device_ip_missing",
                extra_summary=f"device_id={device_id}; channel_id={channel_id}",
            )
            raise HTTPException(status_code=500, detail="Device network information missing")  # i18n
        signal_targets = await _build_signal_targets(db, asset)
        if not signal_targets:
            await _stream_audit(
                db,
                current_user,
                action="play_stream",
                result="failed",
                status_code=503,
                detail="device_transport_unavailable",
                extra_summary=f"device_id={device_id}; channel_id={channel_id}",
            )
            raise _play_http_exception(
                503,
                "device_transport_unavailable",
                "Device signaling transport unavailable",
                "Please verify the device is online, registered, and SIP transport is available",  # C-28
                retryable=True,
            )

        max_streams = _get_max_concurrent_streams()
        if max_streams > 0:
            tenant_id = current_user.tenant_id or "default"
            count_stmt = select(func.count(StreamSession.id)).select_from(StreamSession).join(Asset, StreamSession.asset_id == Asset.id).where(Asset.tenant_id == tenant_id)
            cnt = (await db.execute(count_stmt)).scalar() or 0
            if cnt >= max_streams:
                await _stream_audit(
                    db,
                    current_user,
                    action="play_stream",
                    result="failed",
                    status_code=429,
                    detail="max_concurrent_streams",
                    extra_summary=f"limit={max_streams}; device_id={device_id}; channel_id={channel_id}",
                )
                raise HTTPException(status_code=429, detail=f"Concurrent stream limit reached ({max_streams}), please close some streams first")  # i18n

        if not sip_invite_module.sip_invite:
            await _stream_audit(
                db,
                current_user,
                action="play_stream",
                result="failed",
                status_code=503,
                detail="sip_service_unavailable",
                extra_summary=f"device_id={device_id}; channel_id={channel_id}",
            )
            raise _play_http_exception(
                503,
                "sip_service_unavailable",
                "SIP service not ready",
                "请检查平台 SIP 服务是否已启动完成",
                retryable=True,
            )

        cfg = await _get_gb28181_play_config(db)
        policy_chain = _ssrc_policy_chain(cfg)
        if not bool(cfg.get("ssrc_retry_on_not_ready", True)):
            policy_chain = policy_chain[:1]

        # 1. Check if stream is already active or starting up
        live_session_stream_key = _build_live_session_stream_key(device_id, channel_id)
        existing_ss_stmt = (
            select(StreamSession)
            .where(
                StreamSession.app.in_(["live", "rtp"]),
                StreamSession.asset_id == getattr(asset, "id", None),
                StreamSession.resource_id == getattr(resource, "id", None),
            )
            .order_by(StreamSession.start_time.desc())
        )
        existing_ss = (await db.execute(existing_ss_stmt)).scalars().first()
    
        if existing_ss and existing_ss.stream:
            ss_stream = str(existing_ss.stream or "")
            device_gb_id = str(device_id or "")
            if ss_stream == device_gb_id or ss_stream.startswith(f"{device_gb_id}_") or ss_stream == live_session_stream_key:
                alt_stmt = (
                    select(StreamSession)
                    .where(StreamSession.app.in_(["live", "rtp"]))
                    .where(StreamSession.asset_id == getattr(asset, "id", None))
                    .where(StreamSession.resource_id == getattr(resource, "id", None))
                    .where(StreamSession.call_id.isnot(None))
                    .order_by(StreamSession.start_time.desc())
                )
                alt_ss = (await db.execute(alt_stmt)).scalars().first()
                if alt_ss:
                    existing_ss = alt_ss
    
        stream_session_id = None
        node_id = None
        app_name = "live"
        stream_id = live_session_stream_key
        result = {}
    
        if async_mode:
            default_interval = float(getattr(settings, "STREAM_WAIT_READY_INTERVAL", 0.25) or 0.25)
            default_attempts = int(getattr(settings, "STREAM_WAIT_READY_MAX_ATTEMPTS", 40) or 40)
            chain_len = len(policy_chain) if policy_chain else 1
            next_poll_ms = max(400, min(1200, int(max(default_interval, 0.2) * 1000)))
            timeout_recommend_ms = max(20000, int(default_attempts * max(default_interval, 0.2) * 1000 * chain_len + 6000))
            if existing_ss:
                _record_play_trace(
                    str(existing_ss.id or ""),
                    "async_request_reused",
                    {"device_id": str(device_id or ""), "channel_id": str(channel_id or "")},
                )
                return JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={
                        "code": 202,
                        "msg": "Stream invite sent, please poll status",  # i18n
                        "data": {
                            "session_id": existing_ss.id,
                            "app": existing_ss.app,
                            "stream": existing_ss.stream,
                            "node_id": existing_ss.media_server_id,
                            "next_poll_ms": next_poll_ms,
                            "timeout_recommend_ms": timeout_recommend_ms,
                            "sla": {"accepted_ms": round((time.perf_counter() - req_t0) * 1000, 2), "mode": "async_reuse"},
                        }
                    }
                )
            placeholder_app = "live"
            placeholder_stream = live_session_stream_key or getattr(resource, "gb_id", None) or ""
            placeholder_resource_id = getattr(resource, "id", None)
            placeholder_asset_id = getattr(asset, "id", None)
            if not placeholder_stream or not placeholder_resource_id or not placeholder_asset_id:
                raise _play_http_exception(
                    500,
                    "invalid_stream_session_payload",
                    "会话参数不完整",
                    "请检查设备/通道基础数据完整性后重试",
                    retryable=False,
                    diagnostics={
                        "app": placeholder_app,
                        "stream": placeholder_stream,
                        "resource_id": placeholder_resource_id,
                        "asset_id": placeholder_asset_id,
                    },
                )
            placeholder = StreamSession(
                app=placeholder_app,
                stream=placeholder_stream,
                resource_id=placeholder_resource_id,
                asset_id=placeholder_asset_id,
                tenant_id=current_user.tenant_id,  # S-04 添加租户隔离
                protocol="UDP",
            )
            db.add(placeholder)
            await db.commit()
            await db.refresh(placeholder)
            stream_session_id = placeholder.id
            _record_play_trace(
                stream_session_id,
                "async_request_created",
                {"device_id": str(device_id or ""), "channel_id": str(channel_id or ""), "stream_type": str(stream_type or "main")},
            )
            background_tasks.add_task(
                _async_invite_wait_with_retry,
                stream_session_id=stream_session_id,
                stream_type=stream_type,
                max_attempts=int(getattr(settings, "STREAM_WAIT_READY_MAX_ATTEMPTS", 40)),
                interval_seconds=float(getattr(settings, "STREAM_WAIT_READY_INTERVAL", 0.25)),
            )
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "code": 202,
                    "msg": "Stream invite sent, please poll status",  # i18n
                    "data": {
                        "session_id": stream_session_id,
                        "app": "live",
                        "stream": live_session_stream_key,
                        "node_id": None,
                        "next_poll_ms": next_poll_ms,
                        "timeout_recommend_ms": timeout_recommend_ms,
                        "sla": {"accepted_ms": round((time.perf_counter() - req_t0) * 1000, 2), "mode": "async_new"},
                    }
                }
            )

        attempts: list[dict] = []
        if existing_ss and existing_ss.media_server_id:
            attempts.append({"kind": "reuse"})
        for p in policy_chain:
            attempts.append({"kind": "invite", "policy": p})

        tried: list[str] = []
        last_probe_detail: dict = {}
        last_session_diag: dict = {}
        last_node_host = None
        last_node_http_port = None
        last_app = None
        last_stream = None
        media_mode_candidates = await _resolve_media_mode_candidates(db, getattr(asset, "id", None), asset=asset)

        for attempt in attempts:
            if attempt.get("kind") == "reuse":
                stream_session_id = existing_ss.id
                node_id = existing_ss.media_server_id
                app_name = existing_ss.app or "live"
                stream_id = existing_ss.stream or live_session_stream_key
                # 验证流在 ZLM 上是否仍然活跃
                _reuse_probe_ok = False
                if node_id:
                    try:
                        _reuse_node = get_node_by_id(node_id)
                        if _reuse_node:
                            _reuse_probe_ok, _reuse_found, _ = await _probe_zlm_stream(
                                _reuse_node.get("host", ""),
                                _reuse_node.get("http_port", 80),
                                _reuse_node.get("secret", ""),
                                app_name,
                                stream_id,
                            )
                    except Exception as e:
                        logger.warning(f"Error: {e}")
                    if not _reuse_probe_ok:
                        try:
                            from app.core.media_nodes_db import get_db_media_node_by_id
                            from app.db.session import AsyncSessionLocal
                            _db_host = _db_port = _db_secret = None
                            async with AsyncSessionLocal() as _db_sess:
                                _db_node = await get_db_media_node_by_id(_db_sess, node_id)
                                if _db_node:
                                    _db_host, _db_port, _db_secret = _db_node.host, _db_node.http_port, _db_node.secret
                            if _db_host:
                                _reuse_probe_ok, _reuse_found, _ = await _probe_zlm_stream(
                                    _db_host,
                                    _db_port,
                                    _db_secret,
                                    app_name,
                                    stream_id,
                                )
                        except Exception as e:
                            logger.warning(f"Error: {e}")
                if not _reuse_probe_ok:
                    logger.info(f"[PlayStream] Reuse probe failed for app={app_name} stream={stream_id}, falling back to invite")
                    tried.append("reuse_probe_failed")
                    continue
                result = {
                    "app": app_name,
                    "stream": stream_id,
                    "node_id": node_id,
                    "stream_session_id": stream_session_id,
                    "call_id": existing_ss.call_id,
                    "sdp_ip": existing_ss.media_ip,
                    "media_port": existing_ss.media_port,
                    "media_protocol": existing_ss.protocol,
                    "selection_reason": "reused",
                    "ssrc_policy": "reused",
                }
                tried.append("reused")
                if stream_session_id:
                    _record_play_trace(stream_session_id, "sync_request_reused_session")
            else:
                policy = str(attempt.get("policy") or "adaptive")
                tried.append(policy)
                sent = False
                last_send_exc = None
                current_target = None
                for target_ip, target_port, target_proto_raw in signal_targets:
                    current_target = (target_ip, target_port, _normalize_signal_proto(target_proto_raw))
                    transport_proto = current_target[2]
                    transport = sip_server.get_transport(target_ip, target_port, transport_proto)
                    if transport is None and transport_proto == "TCP":
                        transport_proto = "UDP"
                        transport = sip_server.get_transport(target_ip, target_port, transport_proto)
                    if transport is None:
                        continue
                    for media_mode in media_mode_candidates:
                        try:
                            result = await sip_invite_module.sip_invite.send_invite(
                                asset,
                                resource,
                                ((target_ip, target_port), transport_proto, transport),
                                stream_type=stream_type,
                                zlm_ssrc_check=(policy == "strict"),
                                media_mode_override=media_mode,
                            )
                            sent = True
                            current_target = (target_ip, target_port, transport_proto)
                            break
                        except HTTPException:
                            raise
                        except Exception as exc:
                            last_send_exc = exc
                            continue
                    if sent:
                        break
                if not sent:
                    if last_send_exc:
                        raise _map_play_stream_error(last_send_exc)
                    raise _play_http_exception(
                        503,
                        "device_transport_unavailable",
                        "Device signaling transport unavailable",
                        "请确认设备在线、注册正常且 SIP 传输通道可用",
                        retryable=True,
                    )
                stream_id = result["stream"]
                app_name = result["app"]
                node_id = result.get("node_id")
                stream_session_id = result.get("stream_session_id")
                result["ssrc_policy"] = policy
                if stream_session_id:
                    _record_play_trace(
                        stream_session_id,
                        "sync_invite_sent",
                        {"policy": policy, "signal_target": dict(result.get("signal_target") or {})},
                    )
                if current_target:
                    result["signal_target"] = {
                        "ip": current_target[0],
                        "port": int(current_target[1]),
                        "proto": str(current_target[2]),
                    }

            db_node = await get_db_media_node_by_id(db, node_id) if node_id else None
            node = None if db_node else get_node_by_id(node_id)
            selected_node = db_node or node

            if not selected_node:
                raise HTTPException(status_code=500, detail="Media node information missing")  # i18n

            media_host = None
            media_port = None
            node_host = None
            node_http_port = None
            is_embedded_node = False
            media_item = {}

            if db_node:
                media_host, media_port = db_node.public_host, db_node.public_http_port
                node_host, node_http_port = db_node.host, int(db_node.http_port or 0)
                is_embedded_node = bool(getattr(db_node, "is_embedded", False))
                stream_hints = _build_stream_match_hints(stream_id, str((result or {}).get("ssrc") or ""))
                zlm_probe_ok, zlm_stream_ready, media_item, probe_detail = await _wait_zlm_stream_ready(
                    db_node.host,
                    int(db_node.http_port or 0),
                    str(db_node.secret or ""),
                    app_name,
                    stream_id,
                    max_attempts=int(getattr(settings, "STREAM_WAIT_READY_MAX_ATTEMPTS", 40)),
                    interval_seconds=float(getattr(settings, "STREAM_WAIT_READY_INTERVAL", 0.25)),
                    stream_hints=stream_hints,
                    extra_apps=["rtp"],
                    ssrc=str((result or {}).get("ssrc") or ""),
                )
            else:
                media_host, media_port = node.get("public_host"), node.get("public_http_port")
                is_embedded_node = bool(node.get("is_embedded", False))
                node_host, node_http_port = node.get("host"), int(node.get("http_port") or 0)
                stream_hints = _build_stream_match_hints(stream_id, str((result or {}).get("ssrc") or ""))
                zlm_probe_ok, zlm_stream_ready, media_item, probe_detail = await _wait_zlm_stream_ready(
                    node.get("host") or "",
                    int(node.get("http_port") or 0),
                    str(node.get("secret") or ""),
                    app_name,
                    stream_id,
                    max_attempts=int(getattr(settings, "STREAM_WAIT_READY_MAX_ATTEMPTS", 40)),
                    interval_seconds=float(getattr(settings, "STREAM_WAIT_READY_INTERVAL", 0.25)),
                    stream_hints=stream_hints,
                    extra_apps=["rtp"],
                    ssrc=str((result or {}).get("ssrc") or ""),
                )

            last_probe_detail = probe_detail or {}
            last_node_host = node_host
            last_node_http_port = node_http_port
            last_app = app_name
            last_stream = stream_id

            if not zlm_stream_ready:
                cluster_ready, cluster_node, cluster_media_item, cluster_detail = await _probe_stream_across_nodes(
                    db,
                    app=app_name,
                    stream=stream_id,
                    stream_hints=stream_hints,
                    preferred_node_id=node_id,
                    extra_apps=["rtp"],
                )
                if cluster_ready:
                    zlm_probe_ok = True
                    zlm_stream_ready = True
                    media_item = cluster_media_item
                    probe_detail = {**(probe_detail or {}), **(cluster_detail or {})}
                    node_id = str(cluster_node.get("id") or node_id or "")
                    node_host = str(cluster_node.get("host") or node_host or "")
                    node_http_port = int(cluster_node.get("http_port") or node_http_port or 0)
                    media_host = str(cluster_node.get("public_host") or media_host or "")
                    media_port = int(cluster_node.get("public_http_port") or media_port or 0)
                    is_embedded_node = bool(cluster_node.get("is_embedded", False))
                    selected_node = cluster_node
                else:
                    probe_detail = {**(probe_detail or {}), **(cluster_detail or {})}
                last_probe_detail = probe_detail or {}
                last_node_host = node_host
                last_node_http_port = node_http_port

            if not zlm_probe_ok:
                if stream_session_id:
                    _record_play_trace(
                        stream_session_id,
                        "sync_probe_failed",
                        {"reason": "media_node_unreachable", "node_host": node_host, "node_http_port": node_http_port},
                    )
                await _record_runtime_play_health(
                    db,
                    asset_id=getattr(asset, "id", None),
                    mode=str((result or {}).get("media_protocol") or ""),
                    success=False,
                    status_code=503,
                )
                await db.commit()
                if stream_session_id:
                    with contextlib.suppress(Exception):
                        ss = (
                            await db.execute(select(StreamSession).where(StreamSession.id == stream_session_id))
                        ).scalars().first()
                        if ss:
                            await finalize_stream_session(db, ss, reason="media_node_unreachable")
                            await db.commit()
                raise _play_http_exception(
                    503,
                    "media_node_unreachable",
                    "媒体节点连接失败",
                    "请检查媒体节点服务状态、网络连通性和防火墙配置",
                    retryable=True,
                    diagnostics={"node_host": node_host, "node_http_port": node_http_port, "probe": probe_detail},
                )

            if zlm_stream_ready:
                if stream_session_id:
                    _record_play_trace(
                        stream_session_id,
                        "sync_stream_ready",
                        {"app": app_name, "stream": stream_id, "node_id": str(node_id or "")},
                    )
                await _record_runtime_play_health(
                    db,
                    asset_id=getattr(asset, "id", None),
                    mode=str((result or {}).get("media_protocol") or ""),
                    success=True,
                    status_code=200,
                )
                await db.commit()
                signal_target = (result or {}).get("signal_target") if isinstance(result, dict) else None
                if isinstance(signal_target, dict):
                    hint_ip = str(signal_target.get("ip") or "").strip()
                    hint_port = int(signal_target.get("port") or 0)
                    hint_proto = _normalize_signal_proto(signal_target.get("proto"))
                    if hint_ip and hint_port > 0:
                        _INVITE_ENDPOINT_HINTS[str(asset.gb_id or "").strip()] = {
                            "ip": hint_ip,
                            "port": hint_port,
                            "proto": hint_proto,
                        }
                        if (asset.ip_addr != hint_ip) or int(asset.port or 0) != hint_port:
                            asset.ip_addr = hint_ip
                            asset.port = hint_port
                            asset.transport = hint_proto
                            await db.commit()
                if not media_host or not media_port:
                    media_host, media_port = settings.STREAM_PUBLIC_HOST, settings.STREAM_PUBLIC_HTTP_PORT
            
                url_app = str(probe_detail.get("matched_app") or app_name or "live")
                url_stream = str(probe_detail.get("matched_stream") or stream_id or "")
            
                sla_metrics = {}
                if bool(getattr(settings, "STREAM_SLA_ENABLED", True)):
                    total_ms = round((time.perf_counter() - req_t0) * 1000, 2)
                    sla_metrics = {
                        "mode": "sync_live",
                        "first_frame_ms": total_ms,
                        "total_ms": total_ms,
                        "probe_ready": bool(zlm_stream_ready),
                    }
            
                # 预热 HTTP-FLV 端点（同步模式）——直接 await，确保端点就绪后再返回 URL
                _sync_flv_suffix = "" if url_app == "rtp" else ".live"
                _sync_flv_url = f"http://{node_host}:{node_http_port}/{url_app}/{url_stream}{_sync_flv_suffix}.flv"
                _sync_flv_log = logging.getLogger("stream.warmup")
                await _do_warmup_flv(_sync_flv_url, _sync_flv_log, url_app, url_stream)

                # _build_full_play_response 内部会做 HLS 探测和全量 URL 验证，直接复用
                return await _build_full_play_response(
                    db=db,
                    app_name=url_app,
                    stream_id=url_stream,
                    stream_type=stream_type,
                    selected_node=selected_node,
                    media_host=media_host,
                    media_port=media_port,
                    node_host=node_host,
                    node_http_port=node_http_port,
                    is_embedded_node=is_embedded_node,
                    zlm_probe_ok=zlm_probe_ok,
                    zlm_stream_ready=zlm_stream_ready,
                    media_item=media_item,
                    result=result,
                    resource=resource,
                    node_id=node_id,
                    sla_metrics=sla_metrics,
                )

            if stream_session_id:
                _record_play_trace(
                    stream_session_id,
                    "sync_stream_not_ready",
                    {"policy": str((result or {}).get("ssrc_policy") or ""), "probe": probe_detail or {}},
                )
                await _record_runtime_play_health(
                    db,
                    asset_id=getattr(asset, "id", None),
                    mode=str((result or {}).get("media_protocol") or ""),
                    success=False,
                    status_code=503,
                )
                await db.commit()
                with contextlib.suppress(Exception):
                    ss = (
                        await db.execute(select(StreamSession).where(StreamSession.id == stream_session_id))
                    ).scalars().first()
                    if ss:
                        last_session_diag = {
                            "stream_session_id": str(getattr(ss, "id", "") or ""),
                            "call_id": str(getattr(ss, "call_id", "") or ""),
                            "media_server_id": str(getattr(ss, "media_server_id", "") or ""),
                            "invite_accepted": bool(getattr(ss, "to_tag", None)),
                            "invite_sdp_ip": str(getattr(ss, "media_ip", "") or ""),
                            "invite_media_port": int(getattr(ss, "media_port", 0) or 0) or None,
                            "invite_media_protocol": str(getattr(ss, "protocol", "") or ""),
                            "zlm_ssrc_check": (result.get("zlm_ssrc_check") if isinstance(result, dict) else None),
                        }
                        if getattr(ss, "to_tag", None):
                            await release_stream_session(db, ss, reason="media_stream_not_ready")
                        else:
                            await finalize_stream_session(db, ss, reason="media_stream_not_ready")
                        await db.commit()
                if attempt is not attempts[-1]:
                    await asyncio.sleep(0.8)

        raise _play_http_exception(
            503,
            "media_stream_not_ready",
            "媒体流尚未就绪",
            "请确认设备正在推流并重试，必要时检查设备码流参数和媒体节点负载",
            retryable=True,
            diagnostics={
                "node_host": last_node_host,
                "node_http_port": last_node_http_port,
                "app": last_app,
                "stream": last_stream,
                "probe": last_probe_detail,
                "ssrc_policy_tried": tried,
                "signal_targets_tried": [f"{ip}:{port}/{proto}" for ip, port, proto in (signal_targets or [])],
                "trace": _read_play_trace(str(stream_session_id or "")),
                **(last_session_diag or {}),
            },
        )
    finally:
        await guard.release()


@router.post("/play/{stream_id}/switch")
async def switch_stream_type(
    stream_id: str,
    target_type: str = Query(
        "sub",
        alias="streamType",
        description="目标码流类型: main 或 sub。streamType 为别名，target_type 优先",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    前端交互：将当前播放的码流无缝切换为主码流或子码流（动态升降级）
    实现思路：发送带有新 Subject 的 Re-INVITE 给设备，不拆除现有的 ZLM 端口和播放连接，实现无缝切换。
    """
    if target_type not in ["main", "sub"]:
        raise HTTPException(status_code=400, detail="target_type must be 'main' or 'sub'")  # i18n

    stmt = select(StreamSession).where(StreamSession.stream == stream_id, StreamSession.app == "live", StreamSession.tenant_id == (current_user.tenant_id or "default"))  # M-08 统一租户隔离模式
    result = await db.execute(stmt)
    ss = result.scalars().first()
    if not ss:
        raise HTTPException(status_code=404, detail="Stream session not found")  # i18n
        
    try:
        success = await sip_invite_module.sip_invite.send_stream_switch_reinvite(ss, target_type)
        if not success:
            raise HTTPException(status_code=500, detail="Stream switch signal send failed")  # i18n
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stream switch error: {e}")  # i18n
    
    await _stream_audit(
        db,
        current_user,
        action="switch_stream",
        result="success",
        status_code=200,
        detail=f"Re-INVITE sent to switch to {target_type} stream",  # i18n
        extra_summary=f"stream_id={stream_id}; target={target_type}"
    )
    
    return {"code": 0, "msg": f"Stream switch command sent for {target_type} stream"}  # i18n


@router.post("/stop")
async def stop_stream(
    payload: StopStreamRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    from app.services.stream_session_service import close_stream
    stmt = select(StreamSession).where(StreamSession.tenant_id == (current_user.tenant_id or "default"))  # M-08 统一租户隔离模式
    if payload.app and payload.stream:
        stmt = stmt.where(StreamSession.app == payload.app, StreamSession.stream == payload.stream)
    elif payload.channel_id:
        if payload.device_id:
            stmt = stmt.join(Asset, StreamSession.asset_id == Asset.id).join(
                Resource, StreamSession.resource_id == Resource.id
            ).where(
                Asset.gb_id == payload.device_id,
                Resource.gb_id == payload.channel_id,
                StreamSession.app.in_(["live", "rtp"])
            )
        else:
            stmt = stmt.join(Resource, StreamSession.resource_id == Resource.id).where(
                Resource.gb_id == payload.channel_id,
                StreamSession.app.in_(["live", "rtp"])
            )
    else:
        await _stream_audit(
            db,
            current_user,
            action="stop_stream",
            result="failed",
            status_code=400,
            detail="missing_stream_identity",
        )
        raise HTTPException(status_code=400, detail="Missing stream identifier")  # i18n
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    if not sessions:
        if payload.app and payload.stream:
            try:
                await close_stream(payload.app, payload.stream)
                await _stream_audit(
                    db,
                    current_user,
                    action="stop_stream",
                    result="success",
                    status_code=200,
                    detail="ok",
                    extra_summary=f"stopped=1; mode=close_stream; app={payload.app}; stream={payload.stream[:64]}",
                )
                return {"stopped": 1}
            except Exception:
                await _stream_audit(
                    db,
                    current_user,
                    action="stop_stream",
                    result="partial",
                    status_code=200,
                    detail="close_stream_failed",
                    extra_summary="stopped=0",
                )
                return {"stopped": 0}
        await _stream_audit(
            db,
            current_user,
            action="stop_stream",
            result="success",
            status_code=200,
            detail="no_matching_session",
            extra_summary="stopped=0",
        )
        return {"stopped": 0}
    if not current_user.is_superuser:
        tenant_id = current_user.tenant_id or "default"
        allowed_asset_ids = set(
            (
                await db.execute(
                    select(Asset.id).where(Asset.tenant_id == tenant_id)
                )
            ).scalars().all()
        )
        sessions = [item for item in sessions if item.asset_id in allowed_asset_ids]

    released_infos: list[tuple[str, str, str]] = []  # (app_name, stream_id, ssrc)
    stopped = 0
    for stream_session in sessions:
        app_name = str(getattr(stream_session, "app", "") or "")
        stream_id = str(getattr(stream_session, "stream", "") or "")
        ssrc = str(getattr(stream_session, "ssrc", "") or "")
        if app_name and stream_id and ssrc:
            released_infos.append((app_name, stream_id, ssrc))
        await release_stream_session(db, stream_session, reason="stop_stream_api")
        stopped += 1
    await db.commit()

    # 主动通知插件：让媒体联动/主路分析型插件立即收到 unreg 停止信号
    for app_name, stream_id, ssrc in released_infos:
        ctx = plugin_manager.pop_stream_ctx_by_ssrc(ssrc) or {}
        data: dict[str, Any] = {"sentry_stream_unreg": True}
        data["sentry_stream_type"] = ctx.get("sentry_stream_type", "main") or "main"
        if ctx.get("sentry_channel_id"):
            data["sentry_channel_id"] = ctx.get("sentry_channel_id")
        if ctx.get("sentry_asset_gb_id"):
            data["sentry_asset_gb_id"] = ctx.get("sentry_asset_gb_id")
        _emit_task = asyncio.create_task(plugin_manager.emit("ON_ZLM_STREAM_REG", app_name, stream_id, ssrc, data))
        _emit_task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    await _stream_audit(
        db,
        current_user,
        action="stop_stream",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"stopped={stopped}",
    )
    return {"stopped": stopped}