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
from app.services.stream_session_service import (
    release_stream_session,
    _release_stream_session_no_db,
    _stop_cascade_push_session_no_db,
)
from app.services.audit_center_service import audit_center_service
from app.core.plugin_manager import plugin_manager
from app.core.push_key import parse_push_key, hash_push_key
from app.core.api_key import secure_compare
from app.core.play_token import verify_play_token, extract_token_from_params, should_allow_no_token
from app.api.v1.endpoints.hook_utils import extract_first, is_stream_unreg
from app.core.event_bus import event_bus
from sqlalchemy import select
from datetime import datetime, timezone
import asyncio
from app.core.async_utils import fire_and_forget  # P0-16: 安全的火-忘任务
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
        # P0-02: secret 列已加密存储，需解密后再比较明文
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MediaNode))
            for _node in result.scalars():
                _s = _node.decrypted_secret
                if _s:
                    candidates.add(str(_s).strip())
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


async def _find_media_node_by_secret(session, secret: str | None) -> MediaNode | None:
    """根据 ZLM 回调传入的明文 secret 查找对应媒体节点。

    P0-02: secret 列已加密存储，无法用 SQL ``WHERE secret = ?`` 匹配。
    改为拉取全部节点（通常仅 1-5 条），在 Python 中逐条解密比较。
    若未命中且 secret 等于全局 ``MEDIA_SERVER_SECRET``，回退到内置节点。
    """
    if not secret:
        return None
    result = await session.execute(select(MediaNode))
    for node in result.scalars():
        if node.decrypted_secret == secret:
            return node
    # 回退：ZLM 发送的是全局密钥但 DB 节点 secret 可能不同
    if secret == settings.MEDIA_SERVER_SECRET:
        embedded = await session.execute(select(MediaNode).where(MediaNode.is_embedded.is_(True)).limit(1))
        return embedded.scalars().first()
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
            # P0-02: secret 列已加密存储，无法用 SQL WHERE 匹配，改用辅助函数解密比较
            node = await _find_media_node_by_secret(session, secret)
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


async def _cleanup_sessions(*, app_name: str, stream_id: str, reason: str, ssrc: str = "", cascade_only: bool = False, hook_secret: str = "", hook_data: dict = None, grace_period_seconds: int = 0):
    """R24-01b: 不再持有 DB session 跨慢 I/O。

    Phase1: 独立 session 查询 StreamSession 列表，立即关闭归还连接
    Phase2+3: 对每个 item 调用 _release_stream_session_no_db / _stop_cascade_push_session_no_db
              （内部用独立 session 处理写操作，慢 I/O 在 DB session 外执行）

    P0-RTP: 当 grace_period_seconds > 0 时，跳过 created_at 在宽限期内的会话，
            防止 NAT 穿透中设备的 RTP 超时被误清理。
    """
    # Phase1: 独立 session 查询，立即关闭
    items: list = []
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(StreamSession).where(StreamSession.app == app_name, StreamSession.stream == stream_id)
            if ssrc:
                stmt = stmt.where(StreamSession.ssrc == ssrc)
            result = await session.execute(stmt)
            items = result.scalars().all()
            await session.commit()
    except Exception as e:
        logger.warning(f"[_cleanup_sessions] Phase1 query failed for {app_name}/{stream_id}: {e}")

    # P0-RTP: 宽限期过滤 — 跳过 created_at 在 grace_period_seconds 内的会话
    _now = datetime.now(timezone.utc)
    _skipped = 0
    if grace_period_seconds and grace_period_seconds > 0:
        _filtered = []
        for it in items:
            _created = getattr(it, "created_at", None)
            if _created:
                # 确保 created_at 是 timezone-aware
                if _created.tzinfo is None:
                    _created = _created.replace(tzinfo=timezone.utc)
                _elapsed = (_now - _created).total_seconds()
                if _elapsed < grace_period_seconds:
                    _skipped += 1
                    logger.info(
                        f"[_cleanup_sessions] Skipping session {app_name}/{stream_id} "
                        f"created {_elapsed:.1f}s ago (within grace_period_seconds={grace_period_seconds}s)"
                    )
                    continue
            _filtered.append(it)
        items = _filtered
    if _skipped:
        logger.info(f"[_cleanup_sessions] Skipped {_skipped} session(s) within grace period for {app_name}/{stream_id}")

    # Phase2+3: 对每个 item 调用 _no_db 变体（慢 I/O 不持有 DB session）
    for it in items:
        if cascade_only and str(getattr(it, "from_tag", "") or "") != "cascade_push":
            continue
        if str(getattr(it, "from_tag", "") or "") == "cascade_push":
            await _stop_cascade_push_session_no_db(it, reason)
        else:
            await _release_stream_session_no_db(it, reason=reason)
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
            # R24-01b: Phase1 查询 node 和 stale_sessions，立即关闭 session
            stale_sessions: list = []
            node_id_str = ""
            async with AsyncSessionLocal() as session:
                # P0-02: secret 列已加密存储，改用辅助函数解密比较
                node = await _find_media_node_by_secret(session, secret)
                if node:
                    node_id_str = str(node.id)
                    stale_sessions = (await session.execute(
                        select(StreamSession).where(
                            StreamSession.media_server_id == node_id_str,
                        )
                    )).scalars().all()
                    await session.commit()
            # Phase2+3: 对每个 stale_session 调用 release_stream_session（内部自管理 session）
            for ss in stale_sessions:
                try:
                    async with AsyncSessionLocal() as per_session:
                        await release_stream_session(per_session, ss, reason="zlm_server_restarted")
                except Exception as e:
                    logger.warning(f"[on_server_started] Failed to release stale session: {e}")
            if stale_sessions:
                logger.info(f"[on_server_started] Cleaned up {len(stale_sessions)} stale sessions for ZLM node {node_id_str}")
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
            logger.info(f"on_play: no token but PLAY_ALLOW_NO_TOKEN=True, allowing app={app_name} stream={stream_id}")
            return await _ok()
        _log_play_auth_failure(app_name, stream_id, "missing or invalid play token", data)
        return {"code": 401, "msg": "missing or invalid play token"}

    is_valid, error_msg = verify_play_token(token, app_name, stream_id)
    if not is_valid:
        _log_play_auth_failure(app_name, stream_id, error_msg, data)
        return {"code": 401, "msg": error_msg}

    logger.info(f"on_play auth OK: app={app_name} stream={stream_id}")
    return await _ok()


def _log_play_auth_failure(app: str, stream: str, error_msg: str, data: dict) -> None:
    ip = (data if isinstance(data, dict) else {}).get("ip", "")
    logger.warning(
        "on_play auth FAILED: app=%s stream=%s ip=%s error=%s",
        app, stream, ip, error_msg
    )
    try:
        fire_and_forget(_audit_play_rejection(app, stream, error_msg, ip))  # P0-16: 保存引用防 GC + 异常日志
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
                            PushChannel.push_key_enabled,
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
    # FIX: [2026-07-04] 回放流(playback)和下载流(download)不应开启 MP4 录制，造成存储浪费 [全栈工程师]
    if app_name in ("playback", "download"):
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
            if is_unreg:
                # 流注销，清理会话（R24-01b: _cleanup_sessions 内部自管理 session，不再持有外部 db）
                await _cleanup_sessions(app_name=app_name, stream_id=stream_id, reason="on_stream_changed_unreg", ssrc=ssrc, hook_secret=request.query_params.get("secret", ""), hook_data=data if isinstance(data, dict) else None)
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
                fire_and_forget(plugin_manager.emit("ON_ZLM_STREAM_UNREG", app_name, stream_id, ssrc, data))  # P0-16: 保存引用防 GC + 异常日志
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
                fire_and_forget(plugin_manager.emit("ON_ZLM_STREAM_REG", app_name, stream_id, ssrc, data))  # P0-16: 保存引用防 GC + 异常日志
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
            # R24-01b: _cleanup_sessions 内部自管理 session
            await _cleanup_sessions(app_name=app_name, stream_id=stream_id, reason="on_send_rtp_stopped", ssrc=ssrc, cascade_only=True, hook_secret=request.query_params.get("secret", ""), hook_data=data if isinstance(data, dict) else None)
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
            # P0-RTP: 宽限期检查 — 如果会话刚创建不久（INVITE发送后grace period内），
            # 说明设备可能还在NAT穿透中，此时不应清理会话，而是重新打开RTP服务器等征设备推流
            # P0-RTP: 宽限期检查 — 使用 RTP_TIMEOUT_GRACE_SECONDS 配置
            _grace_period = int(getattr(settings, "RTP_TIMEOUT_GRACE_SECONDS", 20) or 20)
            _should_skip_cleanup = False
            try:
                async with AsyncSessionLocal() as _grace_db:
                    _grace_stmt = select(StreamSession).where(
                        StreamSession.app == app_name,
                        StreamSession.stream == stream_id,
                    ).order_by(StreamSession.created_at.desc()).limit(1)
                    _grace_result = await _grace_db.execute(_grace_stmt)
                    _grace_session = _grace_result.scalars().first()
                    if _grace_session and _grace_session.created_at:
                        from datetime import datetime, timezone
                        _elapsed = (datetime.now(timezone.utc) - _grace_session.created_at).total_seconds()
                        if _elapsed < _grace_period:
                            logger.info(
                                f"[RTP Timeout] Grace period active: elapsed={_elapsed:.1f}s < "
                                f"config={_grace_period}s, re-opening RTP server for {app_name}/{stream_id}"
                            )
                            _should_skip_cleanup = True
                            # 尝试重新打开 RTP 服务器，让设备继续推流
                            try:
                                from app.services.zlm_rtp_server_service import open_rtp_server
                                _rtp_port = int(getattr(settings, "MEDIA_SERVER_RTP_PROXY_PORT", 30000) or 30000)
                                _zlm_host = str(getattr(settings, "MEDIA_SERVER_HOST", "127.0.0.1") or "127.0.0.1")
                                _zlm_http_port = int(getattr(settings, "MEDIA_SERVER_HTTP_PORT", 8880) or 8880)
                                _zlm_secret = str(getattr(settings, "MEDIA_SERVER_SECRET", "") or "")
                                await open_rtp_server(
                                    host=_zlm_host,
                                    http_port=_zlm_http_port,
                                    secret=_zlm_secret,
                                    port=0,  # 让 ZLM 自动分配端口
                                    stream_id=stream_id,
                                    ssrc=ssrc or "0",
                                )
                                logger.info(f"[RTP Timeout] Re-opened RTP server for {app_name}/{stream_id}")
                            except Exception as _reopen_err:
                                logger.warning(
                                    f"[RTP Timeout] Failed to re-open RTP server for {app_name}/{stream_id}: {_reopen_err}"
                                )
                                _should_skip_cleanup = False
            except Exception as _grace_err:
                logger.debug(f"[RTP Timeout] Grace period check failed: {_grace_err}")

            if _should_skip_cleanup:
                logger.info(f"[RTP Timeout] Skipping cleanup for {app_name}/{stream_id} (within grace period)")
            else:
                # Auto-Recovery mechanism
                # We can emit an event here to let a background worker try to send BYE and re-INVITE
                # Or we just clean up session, and let the frontend notice the stream dropped and retry.
                # Here we ensure session is cleanly finalized so a new INVITE can succeed.
                # R24-01b: _cleanup_sessions 内部自管理 session
                # P0-RTP: 传递 grace_period_seconds 给 _cleanup_sessions，
                # 让其跳过宽限期内创建的会话
                await _cleanup_sessions(app_name=app_name, stream_id=stream_id, reason="on_rtp_server_timeout", ssrc=ssrc, hook_secret=request.query_params.get("secret", ""), hook_data=data if isinstance(data, dict) else None, grace_period_seconds=_grace_period)

            # Notify frontend about stream drop
            fire_and_forget(plugin_manager.emit("ON_MEDIA_STREAM_DROPPED", {
                "app": app_name,
                "stream": stream_id,
                "reason": "rtp_timeout"
            }))  # P0-16: 保存引用防 GC + 异常日志
            # FIX: [2026-07-03] 通过告警 WebSocket 通道实时通知前端流中断，使前端可立即停止播放并提示用户 [可靠性工程师]
            try:
                from app.api.v1.endpoints.alarms import alarm_manager
                await alarm_manager.broadcast_alarm({
                    "type": "stream_dropped",
                    "app": app_name,
                    "stream": stream_id,
                    "reason": "rtp_timeout",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message": f"Stream {stream_id} dropped due to RTP timeout",
                }, "default")
            except Exception as _ws_notify_err:
                logger.debug(f"Failed to broadcast stream drop via WebSocket: {_ws_notify_err}")
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
        # R24-01b: _cleanup_sessions 内部自管理 session
        await _cleanup_sessions(app_name=app_name, stream_id=stream_id, ssrc=ssrc or "", reason="on_stream_none_reader", hook_secret=request.query_params.get("secret", ""), hook_data=data if isinstance(data, dict) else None)
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
        # R24-01b: _cleanup_sessions 内部自管理 session
        await _cleanup_sessions(app_name=app_name, stream_id=stream_id, ssrc=ssrc or "", reason="on_stream_none_reader_delayed", hook_secret=hook_secret, hook_data=hook_data)
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
                    nodes_to_check.append((str(db_node.host), int(db_node.http_port or 0), str(db_node.decrypted_secret or "")))  # P0-02: ORM 对象解密
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
                # P-SEC: secret 通过 POST body 传递，避免出现在 URL/代理日志中
                # 变量命名为 post_data（而非 params）以避免与 URL 查询参数混淆
                post_data = {"secret": secret, "vhost": "__defaultVhost__", "app": app_name, "stream": stream_id}
                resp = await client.post(url, data=post_data, timeout=2.0)
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
        # R24-01b: _cleanup_sessions 内部自管理 session
        await _cleanup_sessions(app_name=app_name, stream_id=stream_id, ssrc=ssrc or "", reason="stream_not_found_auto_recovery", hook_secret=request.query_params.get("secret", ""), hook_data=data if isinstance(data, dict) else None)
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
                                fire_and_forget(
                                    sip_invite.send_invite(
                                        asset_gb_id=asset.gb_id,
                                        resource_gb_id=res.gb_id,
                                        app_name=app_name,
                                        stream_id=stream_id,
                                    )
                                )  # P0-16: 保存引用防 GC + 异常日志
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
                    # P0-02: secret 列已加密存储，改用辅助函数解密比较
                    node = await _find_media_node_by_secret(session, secret)
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

            # R25 Stream-2: S3 上传移到 DB session 外，避免上传期间持有 DB 连接导致连接池耗尽
            # （大文件上传可能持续数分钟）
            _s3_upload_pending = _s3_pending
            _s3_upload_raw_file_path = raw_file_path
            _s3_upload_s3_bucket = s3_bucket
            _s3_upload_s3_endpoint = s3_endpoint
            _s3_upload_app_name = app_name
            _s3_upload_stream_id = stream_id
            _s3_upload_start_timestamp = start_timestamp
            _download_ready_asset_gb_id = asset.gb_id if asset else None
            _download_ready_resource_gb_id = resource.gb_id
            _download_ready_effective_url = effective_url

        # R25 Stream-2: S3 上传在 DB session 外执行
        if _s3_upload_pending:
            def _upload_to_s3():
                if not os.path.exists(_s3_upload_raw_file_path):
                    return
                import boto3
                import botocore.exceptions
                try:
                    s3_client = boto3.client(
                        's3',
                        endpoint_url=_s3_upload_s3_endpoint,
                        aws_access_key_id=getattr(settings, "S3_ACCESS_KEY", ""),
                        aws_secret_access_key=getattr(settings, "S3_SECRET_KEY", ""),
                        config=botocore.client.Config(signature_version='s3v4')
                    )
                    s3_key = f"record/{_s3_upload_app_name}/{_s3_upload_stream_id}/{_s3_upload_start_timestamp}.mp4"
                    s3_client.upload_file(_s3_upload_raw_file_path, _s3_upload_s3_bucket, s3_key)
                    logger.info(f"Uploaded record to S3: s3://{_s3_upload_s3_bucket}/{s3_key}")
                    try:
                        os.remove(_s3_upload_raw_file_path)
                    except Exception as e:
                        logger.warning(f"Failed to remove local record file after S3 upload: {e}")
                except Exception as e:
                    logger.error(f"Failed to upload record to S3: {e}")
            try:
                await asyncio.to_thread(_upload_to_s3)
            except Exception as e:
                logger.error(f"S3 upload thread error: {e}")

        if app_name == "download":
            fire_and_forget(plugin_manager.emit("ON_DOWNLOAD_READY", {
                "device_id": _download_ready_asset_gb_id,
                "channel_id": _download_ready_resource_gb_id,
                "stream": stream_id,
                "file_path": _download_ready_effective_url,
                "file_size": file_size,
                "start_time": start_timestamp,
                "time_len": duration
            }))  # P0-16: 保存引用防 GC + 异常日志
            logger.info(f"Download completed for {_download_ready_resource_gb_id}, URL: {_download_ready_effective_url}")
    except Exception as e:
        logger.error(f"Error handling on_record_mp4: {e}")

    return {"code": 0, "msg": "success"}
