from __future__ import annotations

import asyncio
import contextlib
from loguru import logger

# S-11 每个session_id一把锁，防止release和finalize并发清理
_session_locks: dict[str, asyncio.Lock] = {}

from sqlalchemy import select, delete as sql_delete  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.media_nodes_db import get_db_media_node_by_id, release_lease
from app.db.session import AsyncSessionLocal
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.stream_session import StreamSession
from app.services.audit_center_service import audit_center_service
from app.services.zlm_stream_control import close_zlm_stream, _get_zlm_client


async def close_stream(app: str, stream: str, node_id: str | None = None) -> None:
    await close_zlm_stream(app=app, stream=stream, node_id=node_id)


async def _stop_cascade_push_session_no_db(stream_session: StreamSession, reason: str) -> None:
    """R24-01: 不持有 DB session 的级联推送停止逻辑。

    Phase1: 独立 session 读取 node 信息，立即关闭归还连接
    Phase2: 执行 ZLM HTTP stopSendRtp + close_stream（无 DB session 持有）
    Phase3: 独立 session 执行 release_lease + audit log + delete StreamSession
    """
    # Phase1: 读取 node 信息（独立 session，立即关闭）
    node_host: str | None = None
    node_http_port: int = 0
    node_secret: str = ""
    try:
        async with AsyncSessionLocal() as session:
            node = await get_db_media_node_by_id(session, getattr(stream_session, "media_server_id", None))
            if node:
                node_host = node.host
                node_http_port = node.http_port
                # node 为 RuntimeMediaNode，.secret 已是解密后的明文
                node_secret = node.secret
    except Exception as e:
        logger.warning(f"[stop_cascade_push] Failed to query node for app={stream_session.app} stream={stream_session.stream}: {e}")

    if not node_host:
        logger.warning(f"[stop_cascade_push] Media node not found for app={stream_session.app} stream={stream_session.stream}")

    # Phase2: ZLM HTTP stopSendRtp（3s 超时）+ close_stream（2s 超时），无 DB session 持有
    if node_host:
        api_url = f"http://{node_host}:{node_http_port}/index/api/stopSendRtp"
        params = {
            "secret": node_secret,
            "vhost": "__defaultVhost__",
            "app": stream_session.app,
            "stream": stream_session.stream,
        }
        try:
            client = await _get_zlm_client()
            await client.post(api_url, data=params, timeout=3.0)
        except Exception as e:
            logger.warning(f"[stop_cascade_push] ZLM stopSendRtp failed for app={stream_session.app} stream={stream_session.stream}: {e}")

    with contextlib.suppress(Exception):
        await close_stream(stream_session.app, stream_session.stream, getattr(stream_session, "media_server_id", None))

    # Phase3: 独立 session 执行 DB 写操作（release_lease + audit log + delete StreamSession）
    lease_id = getattr(stream_session, "media_port_lease_id", None)
    ss_id = stream_session.id
    try:
        async with AsyncSessionLocal() as session:
            with contextlib.suppress(Exception):
                if lease_id:
                    await release_lease(session, lease_id)
            with contextlib.suppress(Exception):
                await audit_center_service.log(
                    db=session,
                    module="media_nodes",
                    action="stop_send_rtp",
                    operator="system",
                    result="success",
                    summary=f"app={stream_session.app}; stream={stream_session.stream}; reason={reason}",
                )
            if ss_id:
                await session.execute(sql_delete(StreamSession).where(StreamSession.id == ss_id))
            await session.commit()
    except Exception as e:
        logger.error(f"[stop_cascade_push] Phase3 DB writes failed for session {ss_id}: {e}")


async def stop_cascade_push_session(db: AsyncSession, stream_session: StreamSession, reason: str) -> None:
    """R24-01: 保持向后兼容的入口。

    Phase1: 用传入 db 读取 node，commit（但不关闭，保持向后兼容）
    Phase2+3: 执行 ZLM HTTP + 独立 session 写操作

    注意：本函数不再在 DB session 内执行 ZLM HTTP，慢 I/O 独立执行。
    传入的 db 会被 commit 但不会被 close。如需完全释放连接，请使用 _stop_cascade_push_session_no_db。
    """
    # Phase1: 用传入 db 读取 node
    node_host: str | None = None
    node_http_port: int = 0
    node_secret: str = ""
    try:
        node = await get_db_media_node_by_id(db, getattr(stream_session, "media_server_id", None))
        if node:
            node_host = node.host
            node_http_port = node.http_port
            # node 为 RuntimeMediaNode，.secret 已是解密后的明文
            node_secret = node.secret
    except Exception as e:
        logger.warning(f"[stop_cascade_push] Failed to query node: {e}")

    # FIX: [2026-07-17 P1] 不再强制 commit 调用方 session，避免破坏原子性。
    # 改用 flush 将待写操作刷新到 DB，由调用方决定 commit 时机。
    # 原 commit() 会把调用方在同一事务中累计的写操作提前落地，破坏事务原子性。
    try:
        await db.flush()
    except Exception as e:
        logger.warning(f"[stop_cascade_push] flush failed: {e}")
        try:
            await db.rollback()
        except Exception as _rb_err:
            # FIX [2026-07-17 P3-24]: 描述性日志替代静默吞异常
            logger.warning(f"[stop_cascade_push] rollback also failed: {_rb_err}")

    # Phase2: ZLM HTTP stopSendRtp（无 DB session 持有）
    if node_host:
        api_url = f"http://{node_host}:{node_http_port}/index/api/stopSendRtp"
        params = {
            "secret": node_secret,
            "vhost": "__defaultVhost__",
            "app": stream_session.app,
            "stream": stream_session.stream,
        }
        try:
            client = await _get_zlm_client()
            await client.post(api_url, data=params, timeout=3.0)
        except Exception as e:
            logger.warning(f"[stop_cascade_push] ZLM stopSendRtp failed for app={stream_session.app} stream={stream_session.stream}: {e}")
    else:
        logger.warning(f"[stop_cascade_push] Media node not found for app={stream_session.app} stream={stream_session.stream}")

    with contextlib.suppress(Exception):
        await close_stream(stream_session.app, stream_session.stream, getattr(stream_session, "media_server_id", None))

    # Phase3: 独立 session 执行 DB 写操作
    lease_id = getattr(stream_session, "media_port_lease_id", None)
    ss_id = stream_session.id
    try:
        async with AsyncSessionLocal() as session:
            # FIX: [2026-07-17 P1] contextlib.suppress 吞掉所有异常导致资源泄漏，
            # 改为 try/except + logger.exception，确保 release_lease 失败时有日志可查
            if lease_id:
                try:
                    await release_lease(session, lease_id)
                except Exception as e:
                    logger.exception(f"[stop_cascade_push] release_lease failed for lease_id={lease_id}: {e}")
            try:
                await audit_center_service.log(
                    db=session,
                    module="media_nodes",
                    action="stop_send_rtp",
                    operator="system",
                    result="success",
                    summary=f"app={stream_session.app}; stream={stream_session.stream}; reason={reason}",
                )
            except Exception as e:
                logger.warning(f"[stop_cascade_push] audit log failed: {e}")
            if ss_id:
                await session.execute(sql_delete(StreamSession).where(StreamSession.id == ss_id))
            await session.commit()
    except Exception as e:
        logger.error(f"[stop_cascade_push] Phase3 DB writes failed for session {ss_id}: {e}")


async def _release_stream_session_no_db(
    stream_session: StreamSession,
    reason: str = "",
    wait_bye_response: bool = True,
    *,
    asset: Asset | None = None,
    resource: Resource | None = None,
) -> None:
    """R24-01: 不持有 DB session 的流会话释放逻辑。

    所有 DB 读操作（Asset/Resource 查询）由调用方在 Phase1 完成。
    本函数执行：
      Phase2: ZLM close_stream（2s）+ SIP BYE（5s）+ SSRC release + dialog terminate（无 DB session）
      Phase3: 独立 session 执行 release_lease + audit log + delete StreamSession
    """
    import app.sip.invite as sip_invite_module

    # S-11 获取session级别锁，防止与finalize并发清理
    _sid = str(stream_session.id)
    lock = _session_locks.get(_sid)
    if lock is None:
        lock = asyncio.Lock()
        _session_locks[_sid] = lock
    if lock.locked():
        logger.warning(f"[ReleaseStreamSession] Session {_sid} is already being cleaned up, skipping")
        return
    async with lock:
        try:
            channel_id = resource.gb_id if resource else str(stream_session.stream or "").split("_")[0]

            # 捕获所有需要的数据（避免后续 ORM 对象因 commit/close 失效）
            lease_id = getattr(stream_session, "media_port_lease_id", None)
            ssrc_val = str(getattr(stream_session, "ssrc", "") or "")
            call_id = str(getattr(stream_session, "call_id", "") or "")
            from_tag = str(getattr(stream_session, "from_tag", "") or "")
            ss_id = stream_session.id
            app_name = str(getattr(stream_session, "app", "") or "")
            stream_name = str(getattr(stream_session, "stream", "") or "")
            media_server_id = getattr(stream_session, "media_server_id", None)
            media_ip = getattr(stream_session, "media_ip", "") or ""
            media_port = getattr(stream_session, "media_port", "") or ""

            # Phase2-A: 记录 stream health（独立 session，立即关闭）
            if reason == "media_stream_not_ready" or reason == "media_node_unreachable" or reason == "invite_timeout":
                from app.sip.response_handler import _record_stream_health
                try:
                    async with AsyncSessionLocal() as health_db:
                        await _record_stream_health(health_db, stream_session, 503 if reason != "invite_timeout" else 408)
                        await health_db.commit()
                except Exception as e:
                    logger.warning(f"[ReleaseStreamSession] Failed to record stream health: {e}")

            # 释放顺序：先关闭 ZLM 流/端口（防止媒体节点资源泄漏），再发送 BYE，最后删 DB 记录
            bye_sent = False

            # Phase2-B: close_stream（ZLM HTTP 2s 超时）- 无 DB session 持有
            # P2-fix [2026-07-17]: close_stream 失败时记录日志，原 contextlib.suppress 静默吞没
            # 导致 ZLM RTP server 关闭失败时无告警，端口可能泄漏且无日志可查。
            # 对比同文件 line 282-285 的 release_lease 失败有 logger.error，此处保持一致。
            try:
                await close_stream(app_name, stream_name, media_server_id)
            except Exception as _close_stream_err:
                logger.error(
                    f"[ReleaseStreamSession] close_stream failed for app={app_name} "
                    f"stream={stream_name} node_id={media_server_id}: {_close_stream_err}"
                )

            # Phase2-C: 发送 SIP BYE（设备侧清理，5s 超时）- 无 DB session 持有
            if asset and sip_invite_module.sip_invite:
                try:
                    if app_name == "cascade_bypass":
                        from types import SimpleNamespace
                        cascade_dialog = SimpleNamespace(
                            call_id=getattr(stream_session, "cascade_call_id", None) or call_id,
                            from_tag=getattr(stream_session, "cascade_from_tag", None) or from_tag,
                            to_tag=getattr(stream_session, "cascade_to_tag", None) or str(getattr(stream_session, "to_tag", "") or ""),
                            cseq=1,
                        )
                        await sip_invite_module.sip_invite.send_bye(
                            asset, cascade_dialog, channel_id, wait_response=False, timeout_seconds=3.0
                        )
                    else:
                        bye_sent = await sip_invite_module.sip_invite.send_bye(
                            asset, stream_session, channel_id, wait_response=wait_bye_response, timeout_seconds=5.0
                        )
                        if not bye_sent:
                            logger.warning(f"[ReleaseStreamSession] BYE not sent for session {ss_id}, proceeding with cleanup")
                except Exception as e:
                    logger.warning(f"[ReleaseStreamSession] BYE send failed for session {ss_id}: {e}")

            # Phase2-D: SSRC release（Redis）- 无 DB session 持有
            if ssrc_val:
                try:
                    from app.sip.ssrc_manager import ssrc_manager
                    await ssrc_manager.release(ssrc_val)
                except Exception as e:
                    logger.warning(f"[ReleaseStreamSession] Failed to release SSRC {ssrc_val}: {e}")

            # Phase2-E: Dialog terminate（Redis）- 无 DB session 持有
            # S-05 释放流会话时终止Dialog，防止僵尸Dialog干扰后续INVITE
            try:
                if call_id and from_tag:
                    from app.sip.dialog_manager import dialog_manager
                    await dialog_manager.terminate_dialog(call_id, from_tag)
            except Exception as e:
                logger.warning(f"[ReleaseStreamSession] Dialog terminate failed: {e}")

            # Phase3: 独立 session 执行 DB 写操作（release_lease + audit log + delete StreamSession）
            try:
                async with AsyncSessionLocal() as write_db:
                    if lease_id:
                        try:
                            await release_lease(write_db, lease_id)
                        except Exception as e:
                            logger.error(f"[ReleaseStreamSession] Failed to release lease {lease_id}: {e}")

                    if lease_id:
                        with contextlib.suppress(Exception):
                            await audit_center_service.log(
                                db=write_db,
                                module="media_nodes",
                                action="release_rtp_lease",
                                operator="system",
                                result="success",
                                summary=(
                                    f"lease_id={lease_id}; node_id={media_server_id or ''}; "
                                    f"media_ip={media_ip}; media_port={media_port}; "
                                    f"app={app_name}; stream={stream_name}; "
                                    f"reason={reason}; bye_sent={bye_sent}"
                                ),
                            )

                    # C-24 使用SQL delete替代ORM delete，避免commit后对象detached
                    if ss_id:
                        await write_db.execute(sql_delete(StreamSession).where(StreamSession.id == ss_id))
                    await write_db.commit()
            except Exception as e:
                logger.error(f"[ReleaseStreamSession] Phase3 DB writes failed for session {ss_id}: {e}")
        finally:
            _session_locks.pop(_sid, None)


async def release_stream_session(db: AsyncSession, stream_session: StreamSession, reason: str = "", wait_bye_response: bool = True) -> None:
    """R24-01: 保持向后兼容的入口。

    Phase1: 用传入 db 读取 Asset/Resource，commit（但不关闭，保持向后兼容）
    Phase2+3: 调用 _release_stream_session_no_db 执行慢 I/O + 独立 session 写操作

    注意：本函数不再在 DB session 内执行 SIP BYE/ZLM close，慢 I/O 由 _no_db 变体处理。
    传入的 db 会被 commit 但不会被 close（保持向后兼容，调用方的 async with 会负责 close）。
    如需在慢 I/O 期间完全释放连接，请直接调用 _release_stream_session_no_db。
    """
    # Phase1: 用传入 db 读取 Asset/Resource
    asset = None
    try:
        asset = (await db.execute(select(Asset).where(Asset.id == stream_session.asset_id))).scalars().first()
    except Exception as e:
        logger.warning(f"[ReleaseStreamSession] Failed to query Asset {stream_session.asset_id}: {e}")

    resource = None
    if stream_session.resource_id:
        try:
            resource = (
                await db.execute(select(Resource).where(Resource.id == stream_session.resource_id))
            ).scalars().first()
        except Exception as e:
            logger.warning(f"[ReleaseStreamSession] Failed to query Resource {stream_session.resource_id}: {e}")

    # FIX R24-SEVERE: 提交传入的 db（刷新待写），但不关闭（保持向后兼容）
    # 原问题：release_stream_session 在 DB session 内执行 send_bye（5s）+ close_stream（2s），
    #   8 路并发关闭时连接池耗尽（默认 pool_size=10），导致新请求等待连接超时
    # 修复：Phase1 用 db 读取后 commit，Phase2/3 的慢 I/O 和写操作使用独立 session
    # 注意：调用方的 async with 块退出时会 close db，连接在慢 I/O 期间仍被持有，
    #       但已无 pending 写。热路径（hook.py/批量停止）应直接使用 _release_stream_session_no_db。
    try:
        await db.commit()
    except Exception as e:
        logger.warning(f"[ReleaseStreamSession] Phase1 commit failed: {e}")

    # Phase2+3: 慢 I/O + 独立 session 写操作
    await _release_stream_session_no_db(
        stream_session, reason=reason, wait_bye_response=wait_bye_response,
        asset=asset, resource=resource,
    )


async def _finalize_stream_session_no_db(
    stream_session: StreamSession,
    reason: str = "",
    *,
    asset: Asset | None = None,
    resource: Resource | None = None,
) -> None:
    """R24-01: 不持有 DB session 的流会话终结逻辑。

    所有 DB 读操作（Asset/Resource 查询）由调用方在 Phase1 完成。
    本函数执行：
      Phase2: ZLM close_stream + SIP BYE + SSRC release + dialog terminate（无 DB session）
      Phase3: 独立 session 执行 release_lease + audit log + delete StreamSession
    """
    import app.sip.invite as sip_invite_module

    # S-11 获取session级别锁，防止与release并发清理
    _sid = str(stream_session.id)
    lock = _session_locks.get(_sid)
    if lock is None:
        lock = asyncio.Lock()
        _session_locks[_sid] = lock
    if lock.locked():
        logger.warning(f"[FinalizeStreamSession] Session {_sid} is already being cleaned up, skipping")
        return
    async with lock:
        try:
            from_tag = str(getattr(stream_session, "from_tag", "") or "")
            app_name = str(getattr(stream_session, "app", "") or "")

            # 级联推送分支：委托给 _stop_cascade_push_session_no_db
            if app_name == "cascade_push":
                await _stop_cascade_push_session_no_db(stream_session, reason=reason or "finalize")
                return

            # 级联旁路分支
            if app_name == "cascade_bypass":
                channel_id = resource.gb_id if resource else str(stream_session.stream or "").split("_")[0]
                if asset and sip_invite_module.sip_invite:
                    with contextlib.suppress(Exception):
                        from types import SimpleNamespace
                        cascade_dialog = SimpleNamespace(
                            call_id=getattr(stream_session, "cascade_call_id", None) or str(getattr(stream_session, "call_id", "") or ""),
                            from_tag=getattr(stream_session, "cascade_from_tag", None) or from_tag,
                            to_tag=getattr(stream_session, "cascade_to_tag", None) or str(getattr(stream_session, "to_tag", "") or ""),
                            cseq=1,
                        )
                        await sip_invite_module.sip_invite.send_bye(
                            asset, cascade_dialog, channel_id, wait_response=False, timeout_seconds=3.0
                        )
                with contextlib.suppress(Exception):
                    await close_stream(stream_session.app, stream_session.stream, getattr(stream_session, "media_server_id", None))
                bypass_lease_id = getattr(stream_session, "media_port_lease_id", None)
                bypass_ssrc = str(getattr(stream_session, "ssrc", "") or "")
                ss_id = stream_session.id
                # Phase3: 独立 session 写操作
                try:
                    async with AsyncSessionLocal() as session:
                        if bypass_lease_id:
                            with contextlib.suppress(Exception):
                                await release_lease(session, bypass_lease_id)
                        if ss_id:
                            await session.execute(sql_delete(StreamSession).where(StreamSession.id == ss_id))
                        await session.commit()
                except Exception as e:
                    logger.error(f"[FinalizeStreamSession] cascade_bypass Phase3 failed for session {ss_id}: {e}")
                # SSRC release 在 DB session 外
                if bypass_ssrc:
                    with contextlib.suppress(Exception):
                        from app.sip.ssrc_manager import ssrc_manager
                        await ssrc_manager.release(bypass_ssrc)
                return

            # 捕获所有需要的数据
            channel_id = resource.gb_id if resource else str(stream_session.stream or "").split("_")[0]
            lease_id = getattr(stream_session, "media_port_lease_id", None)
            finalize_ssrc = str(getattr(stream_session, "ssrc", "") or "")
            ss_id = stream_session.id
            app_name_str = str(getattr(stream_session, "app", "") or "")
            stream_name = str(getattr(stream_session, "stream", "") or "")
            media_server_id = getattr(stream_session, "media_server_id", None)
            media_ip = getattr(stream_session, "media_ip", "") or ""
            media_port = getattr(stream_session, "media_port", "") or ""

            # Phase2-A: 记录 stream health（独立 session，立即关闭）
            if reason == "media_stream_not_ready" or reason == "media_node_unreachable" or reason == "invite_timeout":
                from app.sip.response_handler import _record_stream_health
                try:
                    async with AsyncSessionLocal() as health_db:
                        await _record_stream_health(health_db, stream_session, 503 if reason != "invite_timeout" else 408)
                        await health_db.commit()
                except Exception as e:
                    logger.warning(f"[FinalizeStreamSession] Failed to record stream health: {e}")

            # Phase2-B: 发送 SIP BYE（3s 超时）- 无 DB session 持有
            if asset and sip_invite_module.sip_invite:
                with contextlib.suppress(Exception):
                    await sip_invite_module.sip_invite.send_bye(
                        asset, stream_session, channel_id, wait_response=False, timeout_seconds=3.0
                    )

            # Phase2-C: close_stream（ZLM HTTP 2s）- 无 DB session 持有
            with contextlib.suppress(Exception):
                await close_stream(app_name_str, stream_name, media_server_id)

            # Phase2-D: SSRC release（Redis）- 无 DB session 持有
            if finalize_ssrc:
                with contextlib.suppress(Exception):
                    from app.sip.ssrc_manager import ssrc_manager
                    await ssrc_manager.release(finalize_ssrc)

            # Phase3: 独立 session 执行 DB 写操作
            try:
                async with AsyncSessionLocal() as write_db:
                    if lease_id:
                        try:
                            await release_lease(write_db, lease_id)
                        except Exception as e:
                            logger.error(f"[FinalizeStreamSession] Failed to release lease {lease_id}: {e}")
                        with contextlib.suppress(Exception):
                            await audit_center_service.log(
                                db=write_db,
                                module="media_nodes",
                                action="release_rtp_lease",
                                operator="system",
                                result="success",
                                summary=(
                                    f"lease_id={lease_id}; node_id={media_server_id or ''}; "
                                    f"media_ip={media_ip}; media_port={media_port}; "
                                    f"app={app_name_str}; stream={stream_name}; "
                                    f"reason={reason}"
                                ),
                            )

                    if ss_id:
                        await write_db.execute(sql_delete(StreamSession).where(StreamSession.id == ss_id))
                    await write_db.commit()
            except Exception as e:
                logger.error(f"[FinalizeStreamSession] Phase3 DB writes failed for session {ss_id}: {e}")
        finally:
            _session_locks.pop(_sid, None)


async def finalize_stream_session(db: AsyncSession, stream_session: StreamSession, reason: str = "") -> None:
    """R24-01: 保持向后兼容的入口。

    Phase1: 用传入 db 读取 Asset/Resource，commit（但不关闭，保持向后兼容）
    Phase2+3: 调用 _finalize_stream_session_no_db 执行慢 I/O + 独立 session 写操作

    注意：本函数不再在 DB session 内执行 SIP BYE/ZLM close，慢 I/O 由 _no_db 变体处理。
    传入的 db 会被 commit 但不会被 close（保持向后兼容，调用方的 async with 会负责 close）。
    如需在慢 I/O 期间完全释放连接，请直接调用 _finalize_stream_session_no_db。
    """
    # Phase1: 用传入 db 读取 Asset/Resource
    asset = None
    try:
        asset = (await db.execute(select(Asset).where(Asset.id == stream_session.asset_id))).scalars().first()
    except Exception as e:
        logger.warning(f"[FinalizeStreamSession] Failed to query Asset {stream_session.asset_id}: {e}")

    resource = None
    if stream_session.resource_id:
        try:
            resource = (
                await db.execute(select(Resource).where(Resource.id == stream_session.resource_id))
            ).scalars().first()
        except Exception as e:
            logger.warning(f"[FinalizeStreamSession] Failed to query Resource {stream_session.resource_id}: {e}")

    # FIX R24-SEVERE: 提交传入的 db（刷新待写），但不关闭（保持向后兼容）
    try:
        await db.commit()
    except Exception as e:
        logger.warning(f"[FinalizeStreamSession] Phase1 commit failed: {e}")

    # Phase2+3: 慢 I/O + 独立 session 写操作
    await _finalize_stream_session_no_db(
        stream_session, reason=reason, asset=asset, resource=resource,
    )
