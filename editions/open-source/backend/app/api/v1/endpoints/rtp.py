from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.api import deps
from app.models.user import User
from app.models.rtp_receive_task import RtpReceiveTask
from app.core.media_nodes_db import get_active_media_node_id, get_db_media_node_by_id, select_best_db_node, allocate_rtp_port_with_lease, release_lease
from app.services.zlm_stream_control import close_zlm_stream
from app.services.auth_audit import safe_auth_audit


router = APIRouter()


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


class RtpReceiveOpenPayload(BaseModel):
    stream_id: str
    app: str = "live"
    ssrc: str | None = None
    tcp_mode: int = 0


@router.post("/receive/open")
async def open_rtp_receive(
    payload: RtpReceiveOpenPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    tenant_id = current_user.tenant_id or "default"
    stream_id = (payload.stream_id or "").strip()
    if not stream_id:
        await safe_auth_audit(
            db,
            module="rtp",
            action="open_rtp_receive",
            source="rtp_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="stream_id_required",
        )
        raise HTTPException(status_code=400, detail="stream_id required")
    app = (payload.app or "live").strip() or "live"
    tcp_mode = int(payload.tcp_mode or 0)
    if tcp_mode not in (0, 1, 2):
        await safe_auth_audit(
            db,
            module="rtp",
            action="open_rtp_receive",
            source="rtp_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="invalid_tcp_mode",
            extra_summary=f"tcp_mode={tcp_mode}",
        )
        raise HTTPException(status_code=400, detail="tcp_mode only supports 0/1/2")

    active_id = None
    try:
        active_id = await get_active_media_node_id(db)
    except Exception:
        active_id = None
    node = await get_db_media_node_by_id(db, active_id) if active_id else None
    if not node:
        node = await select_best_db_node(db)
    if not node:
        await safe_auth_audit(
            db,
            module="rtp",
            action="open_rtp_receive",
            source="rtp_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=503,
            detail="no_media_node",
            extra_summary=f"stream_id={stream_id}",
        )
        raise HTTPException(status_code=503, detail="No available media node configured")

    if getattr(node, "rtp_port_mode", "single") == "single":
        port = node.rtp_port
        lease_id = None
    else:
        lease_id = None
        port = 0
        try:
            _allocated_port, lease_id = await allocate_rtp_port_with_lease(db, node)
            if _allocated_port:
                port = _allocated_port
        except Exception as e:
            logger.warning(f"Error: {e}")

    task = RtpReceiveTask(
        tenant_id=tenant_id,
        node_id=node.id,
        port=int(port),
        lease_id=lease_id,
        app=app,
        stream_id=stream_id,
        ssrc=(payload.ssrc or "").strip() or None,
        tcp_mode=tcp_mode,
        status="running",
        last_error="",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    try:
        from app.services.zlm_rtp_server_service import open_rtp_server
        allocated_port = await open_rtp_server(
            host=str(getattr(node, "host", "") or ""),
            http_port=int(getattr(node, "http_port", 0) or 0),
            secret=str(getattr(node, "secret", "") or ""),
            port=int(port),
            tcp_mode=tcp_mode,
            app=app,
            stream_id=stream_id,
            ssrc=(payload.ssrc or "").strip() or None,
            re_use_port=(getattr(node, "rtp_port_mode", "single") == "single"),
        )
        task.port = int(allocated_port)
        port = int(allocated_port)
        await db.commit()
    except Exception as zlm_err:
        from fastapi import HTTPException
        task.status = "failed"
        task.last_error = str(zlm_err)
        await db.commit()
        err = str(zlm_err).replace(";", ".")[:180]
        await safe_auth_audit(
            db,
            module="rtp",
            action="open_rtp_receive",
            source="rtp_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=int(getattr(zlm_err, "status_code", 502) if isinstance(zlm_err, HTTPException) else 502),
            detail="zlm_open_failed",
            extra_summary=f"task_id={task.id}; stream_id={stream_id}; error={err}",
        )
        try:
            await release_lease(db, lease_id)
            await db.commit()
        except Exception as e:
            logger.warning(f"Error: {e}")
        raise
    except Exception as e:
        task.status = "failed"
        task.last_error = str(e)[:200]
        await db.commit()
        err = str(e).replace(";", ".")[:180]
        await safe_auth_audit(
            db,
            module="rtp",
            action="open_rtp_receive",
            source="rtp_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=502,
            detail="zlm_open_error",
            extra_summary=f"task_id={task.id}; stream_id={stream_id}; error={err}",
        )
        try:
            await release_lease(db, lease_id)
            await db.commit()
        except Exception as e:
            logger.warning(f"Error: {e}")
        raise HTTPException(status_code=502, detail=f"openRtpServer error: {str(e)}")  # FIXED: hardcoded Chinese → English

    await safe_auth_audit(
        db,
        module="rtp",
        action="open_rtp_receive",
        source="rtp_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=(
            f"task_id={task.id}; node_id={node.id}; stream_id={stream_id}; "
            f"app={app}; port={int(port)}; tcp_mode={tcp_mode}"
        ),
    )
    return {
        "task_id": task.id,
        "node_id": node.id,
        "stream_id": stream_id,
        "app": app,
        "port": int(port),
        "public_host": node.public_host,
        "tcp_mode": tcp_mode,
    }


@router.post("/receive/close/{task_id}")
async def close_rtp_receive(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    tid = (task_id or "").strip()
    if not tid:
        await safe_auth_audit(
            db,
            module="rtp",
            action="close_rtp_receive",
            source="rtp_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="task_id_required",
        )
        raise HTTPException(status_code=400, detail="task_id required")
    tenant_id = current_user.tenant_id or "default"
    stmt = select(RtpReceiveTask).where(RtpReceiveTask.id == tid)
    if not current_user.is_superuser:
        stmt = stmt.where(RtpReceiveTask.tenant_id == tenant_id)
    task = (await db.execute(stmt)).scalars().first()
    if not task:
        await safe_auth_audit(
            db,
            module="rtp",
            action="close_rtp_receive",
            source="rtp_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="task_not_found",
            extra_summary=f"task_id={tid}",
        )
        raise HTTPException(status_code=404, detail="task not found")

    try:
        await close_zlm_stream(app=str(task.app or "live"), stream=str(task.stream_id or ""), node_id=str(task.node_id) if task.node_id else None)
    except Exception as e:
        logger.warning(f"Error: {e}")
    try:
        await release_lease(db, getattr(task, "lease_id", None))
    except Exception as e:
        logger.warning(f"Error: {e}")
    task.status = "closed"
    await db.commit()
    await safe_auth_audit(
        db,
        module="rtp",
        action="close_rtp_receive",
        source="rtp_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"task_id={task.id}; stream_id={task.stream_id or ''}; node_id={task.node_id or ''}",
    )
    return {"ok": True, "task_id": task.id, "status": task.status}


@router.get("/receive/{task_id}")
async def get_rtp_receive_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    tid = (task_id or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="task_id required")
    tenant_id = current_user.tenant_id or "default"
    stmt = select(RtpReceiveTask).where(RtpReceiveTask.id == tid)
    if not current_user.is_superuser:
        stmt = stmt.where(RtpReceiveTask.tenant_id == tenant_id)
    task = (await db.execute(stmt)).scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return {
        "task_id": task.id,
        "node_id": task.node_id,
        "stream_id": task.stream_id,
        "app": task.app,
        "port": task.port,
        "status": task.status,
        "last_error": task.last_error or "",
    }
