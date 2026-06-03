from fastapi import APIRouter, Request, HTTPException, Depends
from app.db.session import AsyncSessionLocal
from app.core.config import settings
from app.core.media_nodes import get_media_nodes
from app.models.media_node import MediaNode
from app.models.record import Record
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.stream_session import StreamSession
from app.models.push_channel import PushChannel
from app.services.stream_session_service import stop_cascade_push_session, release_stream_session
from app.services.audit_center_service import audit_center_service
from app.core.plugin_manager import plugin_manager
from app.core.push_key import parse_push_key, hash_push_key
from app.core.api_key import secure_compare
from app.core.play_token import verify_play_token, extract_token_from_params, should_allow_no_token
from app.api.v1.endpoints.hook_utils import extract_first, is_stream_unreg
from app.core.event_bus import event_bus, MediaEventType
from sqlalchemy import select
from datetime import datetime, timezone
import asyncio
import hmac
import os
import time
from loguru import logger

router = APIRouter()


# track delayed none-reader cleanup tasks to prevent GC
_PENDING_NONE_READER_TASKS: set[asyncio.Task] = set()


def _track_none_reader_task(task: asyncio.Task) -> None:
    _PENDING_NONE_READER_TASKS.add(task)
    task.add_done_callback(_PENDING_NONE_READER_TASKS.discard)


# Webhook secret 验证结果内存缓存（减少高频 hook 回调对 DB 的压力）
_ZLM_SECRET_CACHE: dict[str, tuple[bool, float]] = {}
_ZLM_SECRET_CACHE_TTL = 30.0
_ZLM_SECRET_CACHE_MAX = 64


def _prune_secret_cache() -> None:
    now = time.time()
    expired = [k for k, (_, ts) in _ZLM_SECRET_CACHE.items() if (now - ts) > _ZLM_SECRET_CACHE_TTL]
    for k in expired:
        _ZLM_SECRET_CACHE.pop(k, None)
    if len(_ZLM_SECRET_CACHE) > _ZLM_SECRET_CACHE_MAX:
        oldest = sorted(_ZLM_SECRET_CACHE.items(), key=lambda kv: kv[1][1])[:len(_ZLM_SECRET_CACHE) - _ZLM_SECRET_CACHE_MAX]
        for k, _ in oldest:
            _ZLM_SECRET_CACHE.pop(k, None)


async def verify_zlm_secret(secret: str | None = None): # 类型注解不精确
    if not secret:
        raise HTTPException(status_code=403, detail="ZLM secret invalid")
    global_secret = str(settings.MEDIA_SERVER_SECRET or "")
    if global_secret and hmac.compare_digest(str(secret), global_secret):
        return True
    # 2) 内存缓存命中
    now = time.time()
    cached = _ZLM_SECRET_CACHE.get(secret)
    if cached:
        ok, ts = cached
        if (now - ts) < _ZLM_SECRET_CACHE_TTL:
            if ok:
                return True
            raise HTTPException(status_code=403, detail="ZLM secret invalid")
    # 3) 查环境变量节点
    candidates: set[str] = set()
    try:
        for n in get_media_nodes():
            s = (n.get("secret") or "").strip()
            if s:
                candidates.add(s)
    except Exception as e:
        logger.warning(f"Hook callback operation failed: {e}")  # i18n
    if any(hmac.compare_digest(secret, c) for c in candidates):
        _ZLM_SECRET_CACHE[secret] = (True, now)
        return True
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MediaNode.secret))
            for (s,) in result.all():
                if s:
                    candidates.add(str(s).strip())
    except Exception as e:
        logger.warning(f"Hook callback operation failed: {e}")  # i18n
    if any(hmac.compare_digest(secret, c) for c in candidates):
        _ZLM_SECRET_CACHE[secret] = (True, now)
        return True
    _ZLM_SECRET_CACHE[secret] = (False, now)
    _prune_secret_cache()
    logger.warning("ZLM Webhook authentication failed: invalid secret")
    try:
        async with AsyncSessionLocal() as db:
            await audit_center_service.log(
                db=db,
                module="hook",
                action="zlm_secret_verify",
                operator="unauthenticated",
                result="failed",
                summary=(
                    "tenant_id=default; "
                    "source=zlm_hook; "
                    "status_code=403; "
                    "detail=invalid_secret; "
                    "hint=webhook_secret_mismatch"
                ),
            )
    except Exception as e:
        logger.warning(f"Hook callback operation failed: {e}")  # i18n
    raise HTTPException(status_code=403, detail="ZLM secret invalid")


async def _ok() -> dict:
    return {"code": 0, "msg": "success"}


async def _safe_json(request: Request) -> dict | None:
    try:
        return await request.json()
    except Exception:
        logger.warning("Hook 回调 JSON parse failed")
        return None


async def _touch_media_node_by_secret(secret: str | None, data: dict | None = None) -> None:
    """
    根据回调 secret 找到对应媒体节点，更新在线状态/负载。
    - 多节点时可让"运维中心 > 媒体节点"的在线状态随 hook 更新
    """
    if not secret:
        return
    try:
        async with AsyncSessionLocal() as session:
            node = None
            result = await session.execute(select(MediaNode).where(MediaNode.secret == secret))
            node = result.scalars().first()
            if not node:
                if secret == settings.MEDIA_SERVER_SECRET:
                    result = await session.execute(select(MediaNode).where(MediaNode.is_embedded.is_(True)).limit(1))
                    node = result.scalars().first()
            if not node:
                return
            node.is_online = True
            node.last_seen_at = datetime.now(timezone.utc)
            if isinstance(data, dict):
                for key in ("load", "cpu", "mem", "mem_used", "streams", "zlm_streams"):
                    if key in data:
                        try:
                            node.load = float(data.get(key) or 0.0)
                            break
                        except Exception as e:
                            logger.warning(f"Hook回调字段解析跳过: {e}")
                            continue
            await session.commit()
    except Exception as e:
        logger.warning(f"Hook callback operation failed: {e}")  # i18n


async def _cleanup_sessions(db, *, app_name: str, stream_id: str, reason: str, ssrc: str = "", cascade_only: bool = False, hook_secret: str = "", hook_data: dict = None):
    stmt = select(StreamSession).where(StreamSession.app == app_name, StreamSession.stream == stream_id)
    if ssrc:
        stmt = stmt.where(StreamSession.ssrc == ssrc)
    result = await db.execute(stmt)
    items = result.scalars().all()
    for it in items:
        if cascade_only and str(getattr(it, "from_tag", "") or "") != "cascade_push":
            continue
        if str(getattr(it, "from_tag", "") or "") == "cascade_push":
            await stop_cascade_push_session(db, it, reason)
        else:
            await release_stream_session(db, it, reason=reason)
    await _touch_media_node_by_secret(hook_secret, hook_data)


@router.post("/on_server_started", dependencies=[Depends(verify_zlm_secret)])
async def on_server_started(request: Request):
    data = await _safe_json(request)
    if not data:
        return await _ok()
    secret = request.query_params.get("secret")
    await _touch_media_node_by_secret(secret, data if isinstance(data, dict) else None)
    if secret:
        try:
            async with AsyncSessionLocal() as session:
                node = (await session.execute(
                    select(MediaNode).where(MediaNode.secret == secret)
                )).scalars().first()
                if node:
                    stale_sessions = (await session.execute(
                        select(StreamSession).where(
                            StreamSession.media_server_id == str(node.id),
                        )
                    )).scalars().all()
                    for ss in stale_sessions:
                        await release_stream_session(session, ss, reason="zlm_server_restarted")
                    await session.commit()
                    if stale_sessions:
                        logger.info(f"[on_server_started] Cleaned up {len(stale_sessions)} stale sessions for ZLM node {node.id}")
        except Exception as e:
            logger.error(f"[on_server_started] Failed to cleanup stale sessions: {e}")
    return await _ok()


@router.post("/on_server_keepalive", dependencies=[Depends(verify_zlm_secret)])
async def on_server_keepalive(request: Request):
    data = await _safe_json(request)
    if not data:
        return await _ok()
    await _touch_media_node_by_secret(request.query_params.get("secret"), data if isinstance(data, dict) else None)
    return await _ok()


@router.post("/on_play", dependencies=[Depends(verify_zlm_secret)])
async def on_play(request: Request):
    data = await _safe_json(request)
    if not data:
        return await _ok()
    await _touch_media_node_by_secret(request.query_params.get("secret"), data if isinstance(data, dict) else None)

    app_name = (data if isinstance(data, dict) else {}).get("app", "")
    stream_id = (data if isinstance(data, dict) else {}).get("stream", "")
    params = (data if isinstance(data, dict) else {}).get("params")

    token = extract_token_from_params(params)

    if not token:
        if should_allow_no_token():
            logger.info("on_play: no token but PLAY_ALLOW_NO_TOKEN=True, allowing app=%s stream=%s", app_name, stream_id)
            return await _ok()
        _log_play_auth_failure(app_name, stream_id, "missing or invalid play token", data)
        return {"code": 401, "msg": "missing or invalid play token"}

    is_valid, error_msg = verify_play_token(token, app_name, stream_id)
    if not is_valid:
        _log_play_auth_failure(app_name, stream_id, error_msg, data)
        return {"code": 401, "msg": error_msg}

    logger.info("on_play auth OK: app=%s stream=%s", app_name, stream_id)
    return await _ok()


def _log_play_auth_failure(app: str, stream: str, error_msg: str, data: dict) -> None:
    ip = (data if isinstance(data, dict) else {}).get("ip", "")
    logger.warning(
        "on_play auth FAILED: app=%s stream=%s ip=%s error=%s",
        app, stream, ip, error_msg
    )
    try:
        asyncio.create_task(_audit_play_rejection(app, stream, error_msg, ip))
    except Exception as e:
        logger.warning(f"Hook callback operation failed: {e}")  # i18n


async def _audit_play_rejection(app: str, stream: str, error_msg: str, ip: str) -> None:
    try:
        async with AsyncSessionLocal() as db:
            await audit_center_service.log(
                db=db,
                module="hook",
                action="on_play_auth",
                operator="zlm_hook",
                result="failed",
                summary=f"app={app}; stream={stream}; ip={ip}; error={error_msg}",
            )
    except Exception as e:
        logger.warning(f"Hook callback operation failed: {e}")  # i18n


@router.post("/on_publish", dependencies=[Depends(verify_zlm_secret)])
async def on_publish(request: Request):
    """
    处理 ZLM 的 on_publish hook。
    在这里返回 enable_mp4 等控制参数，实现无缝录像。
    """
    data = await _safe_json(request)
    if not data:
        return await _ok()
    await _touch_media_node_by_secret(request.query_params.get("secret"), data if isinstance(data, dict) else None)

    app_name = data.get("app")
    stream_id = data.get("stream")

    def _extract_query_param(payload: dict, key: str) -> str:
        params = payload.get("params")
        if isinstance(params, dict):
            return str(params.get(key) or "").strip()
        if isinstance(params, str):
            raw = params.strip().lstrip("?")
            parts = [p for p in raw.split("&") if p]
            for part in parts:
                if "=" not in part:
                    continue
                k, v = part.split("=", 1)
                if k.strip() == key:
                    return v.strip()
        return ""

    if app_name == "live" and stream_id:
        try:
            async with AsyncSessionLocal() as session:
                pc = (
                    await session.execute(
                        select(PushChannel).where(
                            PushChannel.stream_name == str(stream_id),
                            PushChannel.push_key_enabled == True,
                        )
                    )
                ).scalars().first()
            if pc and pc.hashed_push_key and pc.push_key_prefix:
                push_key_value = _extract_query_param(data if isinstance(data, dict) else {}, "pushKey")
                parsed = parse_push_key(push_key_value)
                if not parsed:
                    return {"code": 401, "msg": "missing pushKey"}
                prefix, raw = parsed
                if prefix != str(pc.push_key_prefix):
                    return {"code": 401, "msg": "invalid pushKey"}
                hashed = hash_push_key(push_key_value, settings.SECRET_KEY)
                if not secure_compare(hashed, str(pc.hashed_push_key)):
                    return {"code": 401, "msg": "invalid pushKey"}
        except Exception as e:
            logger.warning(f"Hook callback operation failed: {e}")  # i18n
            return {"code": 500, "msg": "pushKey check failed"}

    app_name = str(data.get("app", "") or "").strip()
    enable_mp4_default = bool(getattr(settings, "ZLM_DEFAULT_ENABLE_MP4", True))
    if app_name == "rtp":
        enable_mp4_default = False
    result = {
        "code": 0,
        "msg": "success",
        "enable_audio": True,
        "enable_mp4": enable_mp4_default,
    }

    return result


@router.post("/on_stream_changed", dependencies=[Depends(verify_zlm_secret)])
async def on_stream_changed(request: Request):
    data = await _safe_json(request)
    if not data:
        return await _ok()
    await _touch_media_node_by_secret(request.query_params.get("secret"), data if isinstance(data, dict) else None)

    app_name = extract_first(data, ("app", "appName"))
    stream_id = extract_first(data, ("stream", "streamId", "id"))
    ssrc = extract_first(data, ("ssrc",))

    # Infer SSRC from stream_id if ZLM didn't provide it in the webhook
    if not ssrc and stream_id:
        from app.sip.ssrc_manager import ssrc_manager
        looked_up = await ssrc_manager.lookup_ssrc_by_stream(stream_id)
        if looked_up:
            ssrc = looked_up
        else:
            if app_name == "rtp" and len(stream_id) == 8:
                try:
                    ssrc = str(int(stream_id, 16)).zfill(10)
                except ValueError:
                    logger.warning(f"SSRC 解析失败: stream_id={stream_id}")
            if not ssrc and "_" in stream_id:
                possible_ssrc = stream_id.split("_")[-1]
                if possible_ssrc.isdigit() and len(possible_ssrc) == 10:
                    ssrc = possible_ssrc

    # Check if stream is registered or unregistered
    is_unreg = is_stream_unreg(data)

    if app_name and stream_id:
        if is_unreg:
            await event_bus.publish_stream_unregistered(
                app=app_name, stream=stream_id, ssrc=ssrc or "",
                node_id="", raw_data=data if isinstance(data, dict) else {},
            )
        else:
            await event_bus.publish_stream_registered(
                app=app_name, stream=stream_id, ssrc=ssrc or "",
                node_id="", raw_data=data if isinstance(data, dict) else {},
            )

        try:
            async with AsyncSessionLocal() as session:
                if is_unreg:
                    # 流注销，清理会话
                    await _cleanup_sessions(session, app_name=app_name, stream_id=stream_id, reason="on_stream_changed_unreg", ssrc=ssrc, hook_secret=request.query_params.get("secret", ""), hook_data=data if isinstance(data, dict) else None)
                    await session.commit()
                    # 也通知插件：让媒体联动型插件可以停止分析/资源占用
                    if isinstance(data, dict):
                        try:
                            if ssrc:
                                ctx = plugin_manager.pop_stream_ctx_by_ssrc(str(ssrc))
                                if ctx:
                                    data.setdefault("sentry_stream_type", ctx.get("sentry_stream_type", "main"))
                                    if ctx.get("sentry_channel_id"):
                                        data.setdefault("sentry_channel_id", ctx.get("sentry_channel_id"))
                                    if ctx.get("sentry_asset_gb_id"):
                                        data.setdefault("sentry_asset_gb_id", ctx.get("sentry_asset_gb_id"))
                                else:
                                    data.setdefault("sentry_stream_type", "main")
                        except Exception as e:
                            logger.warning(f"Hook callback operation failed: {e}")  # i18n
                        data.setdefault("sentry_stream_unreg", True)
                    asyncio.create_task(plugin_manager.emit("ON_ZLM_STREAM_UNREG", app_name, stream_id, ssrc, data))
                else:
                    # 流注册，触发 SSRC 事件唤醒等待方，消除 play_status 轮询延迟
                    if ssrc:
                        try:
                            from app.sip.invite import notify_ssrc_waiters
                            await notify_ssrc_waiters(str(ssrc))
                            logger.info(f"[Hook] Fired SSRC waiter for ssrc={ssrc}, stream={stream_id}")
                        except Exception as e:
                            logger.warning(f"Hook callback operation failed: {e}")  # i18n
                        # notify_ssrc_waiters() 内部已同时完成 Redis 通知 + 本地 Event.set()
                    # 流注册，异常自愈逻辑：如果 ZLM 报告流上线，但数据库中没有对应的 StreamSession
                    # (比如系统重启导致内存和DB状态不一致)，我们可以选择重建会话或标记
                    # 这里触发一个系统级别的 hook 事件供插件或流媒体管理器消费
                    if isinstance(data, dict) and ssrc:
                        try:
                            ctx = plugin_manager.get_stream_ctx_by_ssrc(str(ssrc))
                            if ctx:
                                data.setdefault("sentry_stream_type", ctx.get("sentry_stream_type"))
                                if ctx.get("sentry_channel_id"):
                                    data.setdefault("sentry_channel_id", ctx.get("sentry_channel_id"))
                                if ctx.get("sentry_asset_gb_id"):
                                    data.setdefault("sentry_asset_gb_id", ctx.get("sentry_asset_gb_id"))
                        except Exception as e:
                            logger.warning(f"Hook callback operation failed: {e}")  # i18n
                    asyncio.create_task(plugin_manager.emit("ON_ZLM_STREAM_REG", app_name, stream_id, ssrc, data))
        except Exception as e:
            logger.error(f"Error handling on_stream_changed: {e}")

    return await _ok()


@router.post("/on_send_rtp_stopped", dependencies=[Depends(verify_zlm_secret)])
async def on_send_rtp_stopped(request: Request):
    data = await _safe_json(request)
    if not data:
        return await _ok()
    await _touch_media_node_by_secret(request.query_params.get("secret"), data if isinstance(data, dict) else None)
    app_name = extract_first(data, ("app", "appName"))
    stream_id = extract_first(data, ("stream", "streamId", "id"))
    ssrc = extract_first(data, ("ssrc",))
    if app_name and stream_id:
        await event_bus.publish_rtp_send_stopped(
            app=app_name, stream=stream_id, ssrc=ssrc or "",
            node_id="", raw_data=data if isinstance(data, dict) else {},
        )
        try:
            async with AsyncSessionLocal() as session:
                await _cleanup_sessions(session, app_name=app_name, stream_id=stream_id, reason="on_send_rtp_stopped", ssrc=ssrc, cascade_only=True, hook_secret=request.query_params.get("secret", ""), hook_data=data if isinstance(data, dict) else None)
                await session.commit()
        except Exception as e:
            logger.warning(f"Hook callback operation failed: {e}")  # i18n
    return await _ok()


@router.post("/on_rtp_server_timeout", dependencies=[Depends(verify_zlm_secret)])
async def on_rtp_server_timeout(request: Request):
    data = await _safe_json(request)
    if not data:
        return await _ok()
    await _touch_media_node_by_secret(request.query_params.get("secret"), data if isinstance(data, dict) else None)
    app_name = extract_first(data, ("app", "appName"))
    stream_id = extract_first(data, ("stream", "streamId", "id"))
    ssrc = extract_first(data, ("ssrc",))

    logger.warning(f"RTP Server Timeout received from ZLM: app={app_name}, stream={stream_id}")

    if app_name and stream_id:
        try:
            async with AsyncSessionLocal() as session:
                # Auto-Recovery mechanism
                # We can emit an event here to let a background worker try to send BYE and re-INVITE
                # Or we just clean up session, and let the frontend notice the stream dropped and retry.
                # Here we ensure session is cleanly finalized so a new INVITE can succeed.
                await _cleanup_sessions(session, app_name=app_name, stream_id=stream_id, reason="on_rtp_server_timeout", ssrc=ssrc, hook_secret=request.query_params.get("secret", ""), hook_data=data if isinstance(data, dict) else None)
                await session.commit()

                # Notify frontend about stream drop
                asyncio.create_task(plugin_manager.emit("ON_MEDIA_STREAM_DROPPED", {
                    "app": app_name,
                    "stream": stream_id,
                    "reason": "rtp_timeout"
                }))
        except Exception as e:
            logger.error(f"Error handling RTP timeout: {e}")
    return await _ok()


@router.post("/on_stream_none_reader", dependencies=[Depends(verify_zlm_secret)])
async def on_stream_none_reader(request: Request):
    """
    当 ZLM 推流无人观看时回调。完整闭环处理：
    - 更新媒体节点活跃状态
    - 发送 SIP BYE 给设备断流（释放摄像头上行带宽）
    - 释放 RTP 端口租约 (防端口泄露)
    - 清理 stream_sessions 数据库记录
    - 告诉 ZLM 彻底关闭该流 (close: True)
    
    智能断流策略：
    - cascade_bypass / cascade 推流会话：不断流（上级平台可能随时请求）
    - playback / download 录像流：不断流（录像进行中）
    - live 实时流：可配置延迟断流（默认立即断流）
    """
    data = await _safe_json(request)
    if not data:
        return {"code": 0, "close": False}
    await _touch_media_node_by_secret(request.query_params.get("secret"), data if isinstance(data, dict) else None)

    app_name = (data or {}).get("app")
    stream_id = (data or {}).get("stream")
    ssrc = extract_first(data, ("ssrc",))
    if not app_name or not stream_id:
        return {"code": 0, "close": False}

    await event_bus.publish_none_reader(
        app=app_name, stream=stream_id,
        node_id="", ssrc=ssrc or "",
        raw_data=data if isinstance(data, dict) else {},
    )

    if app_name in ("cascade_bypass", "cascade"):
        logger.info(f"[none_reader] Keeping cascade stream: {app_name}/{stream_id}")
        return {"code": 0, "close": False}

    if app_name in ("playback", "download"):
        logger.info(f"[none_reader] Keeping recording/playback stream: {app_name}/{stream_id}")
        return {"code": 0, "close": False}

    none_reader_delay = float(getattr(settings, "ZLM_NONE_READER_DELAY_SECONDS", 0) or 0)
    if none_reader_delay > 0 and app_name == "live":
        logger.info(f"[none_reader] Delayed close for live stream: {app_name}/{stream_id}, delay={none_reader_delay}s")
        _t = asyncio.create_task(_delayed_none_reader_cleanup(app_name, stream_id, ssrc, none_reader_delay, request.query_params.get("secret", ""), data if isinstance(data, dict) else None))
        _track_none_reader_task(_t)  # prevent GC of delayed cleanup task
        return {"code": 0, "close": False}

    try:
        async with AsyncSessionLocal() as session:
            await _cleanup_sessions(session, app_name=app_name, stream_id=stream_id, ssrc=ssrc or "", reason="on_stream_none_reader", hook_secret=request.query_params.get("secret", ""), hook_data=data if isinstance(data, dict) else None)
            await session.commit()
    except Exception as e:
        logger.error(f"Error in on_stream_none_reader processing: {e}")

    return {"code": 0, "close": True}


async def _delayed_none_reader_cleanup(app_name: str, stream_id: str, ssrc: str | None, delay: float, hook_secret: str, hook_data: dict | None) -> None:
    try:
        await asyncio.sleep(delay)
        async with AsyncSessionLocal() as check_session:
            check_stmt = select(StreamSession).where(
                StreamSession.app == app_name,
                StreamSession.stream == stream_id,
            )
            if ssrc:
                check_stmt = check_stmt.where(StreamSession.ssrc == int(ssrc) if str(ssrc).isdigit() else StreamSession.ssrc == ssrc)
            check_result = await check_session.execute(check_stmt)
            still_active = check_result.scalars().first()
            if not still_active:
                return
            if ssrc and still_active.ssrc and str(still_active.ssrc) != str(ssrc):
                logger.info(f"[none_reader] SSRC changed during delay for {app_name}/{stream_id}, skipping cleanup")
                return
            node_id = str(getattr(still_active, "media_server_id", "") or "")
        has_viewers = await _check_zlm_has_viewers(app_name, stream_id, node_id)
        if has_viewers:
            logger.info(f"[none_reader] New viewers detected during delay for {app_name}/{stream_id}, keeping stream")
            return
        try:
            from app.services.zlm_stream_control import close_zlm_stream
            await close_zlm_stream(app=app_name, stream=stream_id)
        except Exception as e:
            logger.warning(f"关闭ZLM流失败: {e}")
        async with AsyncSessionLocal() as session:
            await _cleanup_sessions(session, app_name=app_name, stream_id=stream_id, ssrc=ssrc or "", reason="on_stream_none_reader_delayed", hook_secret=hook_secret, hook_data=hook_data)
            await session.commit()
    except Exception as e:
        logger.error(f"Error in _delayed_none_reader_cleanup: {e}")


async def _check_zlm_has_viewers(app_name: str, stream_id: str, node_id: str = "") -> bool:
    try:
        from app.core.media_nodes_db import list_db_media_nodes, get_db_node_by_id
        from app.core.media_nodes import get_media_nodes
        nodes_to_check = []
        if node_id:
            async with AsyncSessionLocal() as session:
                db_node = await get_db_node_by_id(session, node_id)
                if db_node:
                    nodes_to_check.append((str(db_node.host), int(db_node.http_port or 0), str(db_node.secret or "")))
        if not nodes_to_check:
            for n in get_media_nodes():
                nodes_to_check.append((str(n.get("host", "")), int(n.get("http_port", 0) or 0), str(n.get("secret", ""))))
            try:
                async with AsyncSessionLocal() as session:
                    db_nodes = await list_db_media_nodes(session)
                    for n in db_nodes:
                        nodes_to_check.append((str(n.host), int(n.http_port or 0), str(n.secret or "")))
            except Exception as e:
                logger.warning(f"查询媒体节点列表失败: {e}")
        from app.services.zlm_rtp_server_service import get_shared_zlm_client, get_node_client
        for host, http_port, secret in nodes_to_check:
            if not host or http_port <= 0:
                continue
            try:
                client = await get_node_client(host, http_port, node_id) if node_id else await get_shared_zlm_client()
                url = f"http://{host}:{http_port}/index/api/getMediaList"
                params = {"secret": secret, "vhost": "__defaultVhost__", "app": app_name, "stream": stream_id}
                resp = await client.get(url, params=params, timeout=2.0)
                data = resp.json()
                if data.get("code") in (0, "0") and isinstance(data.get("data"), list):
                    for item in data["data"]:
                        reader_count = int(item.get("readerCount", 0) or 0)
                        if reader_count > 0:
                            return True
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"检查ZLM观看者失败: {e}")
    return False


@router.post("/on_stream_not_found", dependencies=[Depends(verify_zlm_secret)])
async def on_stream_not_found(request: Request):
    """
    当播放器请求的流不存在时回调。
    这是 RTP 流超时检测与信令自愈（Auto-Recovery）的关键点。
    如果 SIP 信令依然存活，但 ZLM 流丢失（例如网络抖动导致设备断流），
    我们可以在这里自动发送 BYE 清理僵尸会话，甚至触发重新拉流。
    """
    data = await _safe_json(request)
    if not data:
        return {"code": 0, "msg": "ignored"}
    await _touch_media_node_by_secret(request.query_params.get("secret"), data if isinstance(data, dict) else None)

    app_name = (data or {}).get("app")
    stream_id = (data or {}).get("stream")
    ssrc = extract_first(data, ("ssrc",))
    if not app_name or not stream_id:
        return {"code": 0, "msg": "ignored"}

    logger.info(
        "Stream not found for %s/%s. Possible causes: stream not yet registered, HLS not enabled, or RTP data not arrived. Triggering auto-recovery check.",
        app_name, stream_id
    )
    try:
        async with AsyncSessionLocal() as session:
            await _cleanup_sessions(session, app_name=app_name, stream_id=stream_id, ssrc=ssrc or "", reason="stream_not_found_auto_recovery", hook_secret=request.query_params.get("secret", ""), hook_data=data if isinstance(data, dict) else None)
            await session.commit()
    except Exception as e:
        logger.error(f"Error in on_stream_not_found processing: {e}")

    # Auto-play: if stream not found, check if there's a matching device channel and auto-invite
    if settings.AUTO_PLAY_ENABLED if hasattr(settings, 'AUTO_PLAY_ENABLED') else False:
        try:
            async with AsyncSessionLocal() as session:
                # Try to find a resource matching the stream_id (which is typically the channel GB ID)
                res = (await session.execute(
                    select(Resource).where(Resource.gb_id == stream_id, Resource.node_type == "channel")
                )).scalars().first()
                if res:
                    asset = (await session.execute(
                        select(Asset).where(Asset.id == res.asset_id)
                    )).scalars().first()
                    if asset and asset.status:
                        # Check if there's already an active stream session for this channel
                        existing = (await session.execute(
                            select(StreamSession).where(
                                StreamSession.stream == stream_id,
                                StreamSession.app == app_name,
                            )
                        )).scalars().first()
                        if not existing:
                            logger.info(f"[AutoPlay] Stream not found for {app_name}/{stream_id}, auto-inviting device {asset.gb_id}")
                            from app.sip.invite import sip_invite
                            if sip_invite:
                                _auto_play_task = asyncio.create_task(
                                    sip_invite.send_invite(
                                        asset_gb_id=asset.gb_id,
                                        resource_gb_id=res.gb_id,
                                        app_name=app_name,
                                        stream_id=stream_id,
                                    )
                                )
                                _auto_play_task.add_done_callback(lambda t: t.exception() if not t.cancelled() and t.exception() else None)
        except Exception as e:
            logger.warning(f"[AutoPlay] Auto-play failed for {app_name}/{stream_id}: {e}")

    return {"code": 0, "msg": "success"}

@router.post("/on_record_mp4", dependencies=[Depends(verify_zlm_secret)])
async def on_record_mp4(request: Request):
    """
    Handle MP4 recording completion from ZLMediaKit
    """
    data = await _safe_json(request)
    if not data:
        return await _ok()
    logger.info(f"Received MP4 Record: {data}")
    
    app_name = data.get("app")
    stream_id = data.get("stream")
    file_path = data.get("file_path")
    file_size = data.get("file_size")
    start_timestamp = data.get("start_time")
    duration = data.get("time_len")
    url = data.get("url")
    
    if not stream_id or not start_timestamp or not duration:
        return {"code": 0, "msg": "ignored"}

    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Resource).where(Resource.gb_id == stream_id)
            result = await session.execute(stmt)
            resource = result.scalars().first()
            if not resource and "_" in str(stream_id or ""):
                base_stream = str(stream_id).split("_", 1)[0]
                if base_stream:
                    result = await session.execute(select(Resource).where(Resource.gb_id == base_stream))
                    resource = result.scalars().first()
            
            if not resource or not getattr(resource, "asset_id", None):
                return {"code": 0, "msg": "ignored"}
            asset = (await session.execute(select(Asset).where(Asset.id == resource.asset_id))).scalars().first()
            media_node_id = None
            node = None
            try:
                secret = request.query_params.get("secret")
                if secret:
                    node = (await session.execute(select(MediaNode).where(MediaNode.secret == secret))).scalars().first()
                    if node:
                        media_node_id = str(node.id)
            except Exception as e:
                logger.warning(f"Hook callback operation failed: {e}")  # i18n
                media_node_id = None

            def _is_http(s: str) -> bool:
                return s.startswith("http://") or s.startswith("https://")

            def _derive_record_path(value: str) -> str:
                v = (value or "").strip()
                if "/record/" in v:
                    idx = v.find("/record/")
                    return v[idx:]
                return ""

            effective_url = str(url or "").strip()
            raw_file_path = str(file_path or "").strip()
            if (not effective_url) or (not _is_http(effective_url)):
                if _is_http(raw_file_path):
                    effective_url = raw_file_path
                else:
                    path = _derive_record_path(raw_file_path)
                    if node and path:
                        public_host = (
                            (getattr(node, "stream_ip", None) or "").strip()
                            or (getattr(node, "public_ip", None) or "").strip()
                            or (str(getattr(settings, "STREAM_PUBLIC_HOST", "") or "").strip())
                            or (getattr(node, "ip", None) or "").strip()
                        )
                        public_http_port = int(getattr(settings, "STREAM_PUBLIC_HTTP_PORT", 0) or 0) or int(getattr(node, "http_port", 0) or 0)
                        if public_host:
                            base = f"http://{public_host}" if public_http_port in {0, 80} else f"http://{public_host}:{public_http_port}"
                            if not path.startswith("/"):
                                path = f"/{path}"
                            effective_url = f"{base}{path}"

            effective_url = effective_url or raw_file_path
            if not effective_url:
                return {"code": 0, "msg": "ignored"}
                
            s3_bucket = getattr(settings, "S3_BUCKET", "")
            s3_endpoint = getattr(settings, "S3_ENDPOINT", "")
            _s3_pending = bool(s3_bucket and s3_endpoint and raw_file_path)

            try:
                ts_val = int(float(start_timestamp))
                dur_val = int(float(duration))
            except (ValueError, TypeError):
                logger.warning(f"on_record_mp4: invalid timestamp/duration: start={start_timestamp} duration={duration}")
                return {"code": 0, "msg": "ignored"}
            start_dt = datetime.fromtimestamp(ts_val, tz=timezone.utc).replace(tzinfo=None)
            end_dt = datetime.fromtimestamp(ts_val + dur_val, tz=timezone.utc).replace(tzinfo=None)
            record = Record(
                asset_id=resource.asset_id,
                resource_id=resource.id,
                start_time=start_dt,
                end_time=end_dt,
                duration=float(duration or 0),
                file_path=effective_url,
                file_size=int(file_size or 0),
                stream_id=str(stream_id),
                tenant_id=((asset.tenant_id if asset else "default") or "default"),
                record_app=(str(app_name) if app_name else None),
                media_node_id=media_node_id,
                zlm_file_path=(raw_file_path if raw_file_path else None),
                url_ok=True,
                url_error="",
            )
            session.add(record)
            await session.commit()
            logger.info(f"Saved record for {stream_id} app={app_name}: {duration}s")

            if _s3_pending:
                def _upload_to_s3():
                    if not os.path.exists(raw_file_path):
                        return
                    import boto3
                    import botocore.exceptions
                    try:
                        s3_client = boto3.client(
                            's3',
                            endpoint_url=s3_endpoint,
                            aws_access_key_id=getattr(settings, "S3_ACCESS_KEY", ""),
                            aws_secret_access_key=getattr(settings, "S3_SECRET_KEY", ""),
                            config=botocore.client.Config(signature_version='s3v4')
                        )
                        s3_key = f"record/{app_name}/{stream_id}/{start_timestamp}.mp4"
                        s3_client.upload_file(raw_file_path, s3_bucket, s3_key)
                        logger.info(f"Uploaded record to S3: s3://{s3_bucket}/{s3_key}")
                        try:
                            os.remove(raw_file_path)
                        except Exception as e:
                            logger.warning(f"Failed to remove local record file after S3 upload: {e}")
                    except Exception as e:
                        logger.error(f"Failed to upload record to S3: {e}")
                try:
                    await asyncio.to_thread(_upload_to_s3)
                except Exception as e:
                    logger.error(f"S3 upload thread error: {e}")
            
            if app_name == "download":
                asyncio.create_task(plugin_manager.emit("ON_DOWNLOAD_READY", {
                    "device_id": asset.gb_id if asset else None,
                    "channel_id": resource.gb_id,
                    "stream": stream_id,
                    "file_path": effective_url,
                    "file_size": file_size,
                    "start_time": start_timestamp,
                    "time_len": duration
                }))
                logger.info(f"Download completed for {resource.gb_id}, URL: {effective_url}")
    except Exception as e:
        logger.error(f"Error handling on_record_mp4: {e}")
            
    return {"code": 0, "msg": "success"}