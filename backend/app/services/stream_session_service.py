from __future__ import annotations

import asyncio
import contextlib
from loguru import logger

# S-11 每个session_id一把锁，防止release和finalize并发清理
_session_locks: dict[str, asyncio.Lock] = {}

from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.media_nodes_db import get_db_media_node_by_id, release_lease
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.stream_session import StreamSession
from app.services.audit_center_service import audit_center_service
from app.services.zlm_stream_control import close_zlm_stream, _get_zlm_client


async def close_stream(app: str, stream: str, node_id: str | None = None) -> None:
    await close_zlm_stream(app=app, stream=stream, node_id=node_id)


async def stop_cascade_push_session(db: AsyncSession, stream_session: StreamSession, reason: str) -> None:
    node = await get_db_media_node_by_id(db, getattr(stream_session, "media_server_id", None))
    if node:
        api_url = f"http://{node.host}:{node.http_port}/index/api/stopSendRtp"
        params = {
            "secret": node.secret,
            "vhost": "__defaultVhost__",
            "app": stream_session.app,
            "stream": stream_session.stream,
        }
        try:
            client = await _get_zlm_client()
            await client.post(api_url, data=params, timeout=3.0)
        except Exception as e:
            logger.warning(f"[stop_cascade_push] ZLM stopSendRtp failed for app={stream_session.app} stream={stream_session.stream} node={node.id}: {e}")
    else:
        logger.warning(f"[stop_cascade_push] Media node not found for app={stream_session.app} stream={stream_session.stream}")

    with contextlib.suppress(Exception):
        await close_stream(stream_session.app, stream_session.stream, getattr(stream_session, "media_server_id", None))
    # close_stream suppress is acceptable - best-effort cleanup, failure logged by close_stream itself

    with contextlib.suppress(Exception):
        lease_id = getattr(stream_session, "media_port_lease_id", None)
        if lease_id:
            await release_lease(db, lease_id)

    with contextlib.suppress(Exception):
        await audit_center_service.log(
            db=db,
            module="media_nodes",
            action="stop_send_rtp",
            operator="system",
            result="success",
            summary=f"app={stream_session.app}; stream={stream_session.stream}; reason={reason}",
        )

    await db.delete(stream_session)


async def release_stream_session(db: AsyncSession, stream_session: StreamSession, reason: str = "", wait_bye_response: bool = True) -> None:
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
            asset = None
            try:
                asset = (await db.execute(select(Asset).where(Asset.id == stream_session.asset_id))).scalars().first()
            except Exception as e:
                # contextlib.suppress(Exception) → explicit log for Asset query failure
                logger.warning(f"[ReleaseStreamSession] Failed to query Asset {stream_session.asset_id}: {e}")

            if reason == "media_stream_not_ready" or reason == "media_node_unreachable" or reason == "invite_timeout":
                from app.sip.response_handler import _record_stream_health
                try:
                    await _record_stream_health(db, stream_session, 503 if reason != "invite_timeout" else 408)
                    await db.commit()
                except Exception as e:
                    # contextlib.suppress(Exception) → explicit log for stream health record
                    logger.warning(f"[ReleaseStreamSession] Failed to record stream health: {e}")

            resource = None
            if stream_session.resource_id:
                try:
                    resource = (
                        await db.execute(select(Resource).where(Resource.id == stream_session.resource_id))
                    ).scalars().first()
                except Exception as e:
                    # contextlib.suppress(Exception) → explicit log for Resource query failure
                    logger.warning(f"[ReleaseStreamSession] Failed to query Resource {stream_session.resource_id}: {e}")

            channel_id = resource.gb_id if resource else str(stream_session.stream or "").split("_")[0]

            # 释放顺序：先关闭 ZLM 流/端口（防止媒体节点资源泄漏），再发送 BYE，最后删 DB 记录
            bye_sent = False
            lease_id = getattr(stream_session, "media_port_lease_id", None)

            with contextlib.suppress(Exception):
                await close_stream(stream_session.app, stream_session.stream, getattr(stream_session, "media_server_id", None))

            # 2) 释放端口租约
            if lease_id:
                try:
                    await release_lease(db, lease_id)
                except Exception as e:
                    logger.error(f"[ReleaseStreamSession] Failed to release lease {lease_id}: {e}")

            # 3) 发送 SIP BYE（设备侧清理）
            if asset and sip_invite_module.sip_invite:
                try:
                    app_name = str(getattr(stream_session, "app", "") or "")
                    if app_name == "cascade_bypass":
                        from types import SimpleNamespace
                        cascade_dialog = SimpleNamespace(
                            call_id=getattr(stream_session, "cascade_call_id", None) or stream_session.call_id,
                            from_tag=getattr(stream_session, "cascade_from_tag", None) or stream_session.from_tag,
                            to_tag=getattr(stream_session, "cascade_to_tag", None) or stream_session.to_tag,
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
                            logger.warning(f"[ReleaseStreamSession] BYE not sent for session {stream_session.id}, proceeding with cleanup")
                except Exception as e:
                    # contextlib.suppress(Exception) → explicit log for BYE send failure
                    logger.warning(f"[ReleaseStreamSession] BYE send failed for session {stream_session.id}: {e}")

            # 4) 审计日志
            if lease_id:
                with contextlib.suppress(Exception):
                    await audit_center_service.log(
                        db=db,
                        module="media_nodes",
                        action="release_rtp_lease",
                        operator="system",
                        result="success",
                        summary=(
                            f"lease_id={lease_id}; node_id={getattr(stream_session, 'media_server_id', '') or ''}; "
                            f"media_ip={getattr(stream_session, 'media_ip', '') or ''}; media_port={getattr(stream_session, 'media_port', '') or ''}; "
                            f"app={getattr(stream_session, 'app', '') or ''}; stream={getattr(stream_session, 'stream', '') or ''}; "
                            f"reason={reason}; bye_sent={bye_sent}"
                        ),
                    )

            ssrc_val = str(getattr(stream_session, "ssrc", "") or "")
            if ssrc_val:
                try:
                    from app.sip.ssrc_manager import ssrc_manager
                    await ssrc_manager.release(ssrc_val)
                except Exception as e:
                    # contextlib.suppress(Exception) → explicit log for SSRC release failure
                    logger.warning(f"[ReleaseStreamSession] Failed to release SSRC {ssrc_val}: {e}")
            # S-05 释放流会话时终止Dialog，防止僵尸Dialog干扰后续INVITE
            try:
                _call_id = str(getattr(stream_session, "call_id", "") or "")
                _from_tag = str(getattr(stream_session, "from_tag", "") or "")
                if _call_id and _from_tag:
                    from app.sip.dialog_manager import dialog_manager
                    await dialog_manager.terminate_dialog(_call_id, _from_tag)
            except Exception as e:
                logger.debug(f"[ReleaseStreamSession] Dialog terminate failed: {e}")
            # C-24 使用SQL delete替代ORM delete，避免commit后对象detached
            from sqlalchemy import delete as sql_delete
            _del_id = stream_session.id
            if _del_id:
                await db.execute(sql_delete(StreamSession).where(StreamSession.id == _del_id))
            await db.commit()
        finally:
            _session_locks.pop(_sid, None)


async def finalize_stream_session(db: AsyncSession, stream_session: StreamSession, reason: str = "") -> None:
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

            if app_name == "cascade_push":
                await stop_cascade_push_session(db, stream_session, reason=reason or "finalize")
                return

            if app_name == "cascade_bypass":
                asset = None
                with contextlib.suppress(Exception):
                    asset = (await db.execute(select(Asset).where(Asset.id == stream_session.asset_id))).scalars().first()
                resource = None
                if stream_session.resource_id:
                    with contextlib.suppress(Exception):
                        resource = (
                            await db.execute(select(Resource).where(Resource.id == stream_session.resource_id))
                        ).scalars().first()
                channel_id = resource.gb_id if resource else str(stream_session.stream or "").split("_")[0]
                if asset and sip_invite_module.sip_invite:
                    with contextlib.suppress(Exception):
                        from types import SimpleNamespace
                        cascade_dialog = SimpleNamespace(
                            call_id=getattr(stream_session, "cascade_call_id", None) or stream_session.call_id,
                            from_tag=getattr(stream_session, "cascade_from_tag", None) or stream_session.from_tag,
                            to_tag=getattr(stream_session, "cascade_to_tag", None) or stream_session.to_tag,
                            cseq=1,
                        )
                        await sip_invite_module.sip_invite.send_bye(
                            asset, cascade_dialog, channel_id, wait_response=False, timeout_seconds=3.0
                        )
                with contextlib.suppress(Exception):
                    await close_stream(stream_session.app, stream_session.stream, getattr(stream_session, "media_server_id", None))
                bypass_lease_id = getattr(stream_session, "media_port_lease_id", None)
                if bypass_lease_id:
                    with contextlib.suppress(Exception):
                        from app.core.media_nodes_db import release_lease
                        await release_lease(db, bypass_lease_id)
                bypass_ssrc = str(getattr(stream_session, "ssrc", "") or "")
                if bypass_ssrc:
                    with contextlib.suppress(Exception):
                        from app.sip.ssrc_manager import ssrc_manager
                        await ssrc_manager.release(bypass_ssrc)
                await db.delete(stream_session)
                await db.commit()
                return

            # Record stream health if it's a failure reason
            if reason == "media_stream_not_ready" or reason == "media_node_unreachable" or reason == "invite_timeout":
                from app.sip.response_handler import _record_stream_health
                with contextlib.suppress(Exception):
                    await _record_stream_health(db, stream_session, 503 if reason != "invite_timeout" else 408)
                    await db.commit()

            # Send SIP BYE to device for normal sessions
            asset = None
            try:
                asset = (await db.execute(select(Asset).where(Asset.id == stream_session.asset_id))).scalars().first()
            except Exception as e:
                # contextlib.suppress(Exception) → explicit log for Asset query failure
                logger.warning(f"[FinalizeStreamSession] Failed to query Asset {stream_session.asset_id}: {e}")
            resource = None
            if stream_session.resource_id:
                try:
                    resource = (
                        await db.execute(select(Resource).where(Resource.id == stream_session.resource_id))
                    ).scalars().first()
                except Exception as e:
                    # contextlib.suppress(Exception) → explicit log for Resource query failure
                    logger.warning(f"[FinalizeStreamSession] Failed to query Resource {stream_session.resource_id}: {e}")
            channel_id = resource.gb_id if resource else str(stream_session.stream or "").split("_")[0]
            if asset and sip_invite_module.sip_invite:
                with contextlib.suppress(Exception):
                    await sip_invite_module.sip_invite.send_bye(
                        asset, stream_session, channel_id, wait_response=False, timeout_seconds=3.0
                    )

            with contextlib.suppress(Exception):
                await close_stream(stream_session.app, stream_session.stream, getattr(stream_session, "media_server_id", None))

            lease_id = getattr(stream_session, "media_port_lease_id", None)
            if lease_id:
                try:
                    await release_lease(db, lease_id)
                except Exception as e:
                    logger.error(f"[FinalizeStreamSession] Failed to release lease {lease_id}: {e}")
                with contextlib.suppress(Exception):
                    await audit_center_service.log(
                        db=db,
                        module="media_nodes",
                        action="release_rtp_lease",
                        operator="system",
                        result="success",
                        summary=(
                            f"lease_id={lease_id}; node_id={getattr(stream_session, 'media_server_id', '') or ''}; "
                            f"media_ip={getattr(stream_session, 'media_ip', '') or ''}; media_port={getattr(stream_session, 'media_port', '') or ''}; "
                            f"app={getattr(stream_session, 'app', '') or ''}; stream={getattr(stream_session, 'stream', '') or ''}; "
                            f"reason={reason}"
                        ),
                    )

            finalize_ssrc = str(getattr(stream_session, "ssrc", "") or "")
            if finalize_ssrc:
                with contextlib.suppress(Exception):
                    from app.sip.ssrc_manager import ssrc_manager
                    await ssrc_manager.release(finalize_ssrc)

            await db.delete(stream_session)
            await db.commit()
        finally:
            _session_locks.pop(_sid, None)
