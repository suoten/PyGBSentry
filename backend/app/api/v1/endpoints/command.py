"""移动指挥会商会话与指令 API。"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.models.command_instruction import CommandInstruction
from app.models.command_session import CommandSession
from app.models.command_participant import CommandParticipant
from app.services.auth_audit import safe_auth_audit

router = APIRouter()


class CommandSessionCreate(BaseModel):
    alarm_id: str | None = None
    title: str | None = None


class CommandSessionJoin(BaseModel):
    role: str = "participant"


class CommandSessionClose(BaseModel):
    summary: str | None = None


class CommandInstructionCreate(BaseModel):
    session_id: str
    content: str


def _tenant_id(user: User) -> str:
    return user.tenant_id or "default"


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


def _duration_sec(started_at: datetime | None, ended_at: datetime | None) -> int:
    """FIX: [2026-08-22 P1] GET /command/sessions 对 open 会话的 duration 计算混用
    aware/naive：DB 列为 naive DateTime，ended_at 为 None 时以 aware 的
    datetime.now(timezone.utc) 兜底再与 naive started_at 相减 → TypeError → 500。
    统一折算为 naive UTC 后求差（ended_at 若为 aware 一并归一化）。
    """

    def _to_naive_utc(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    start = _to_naive_utc(started_at)
    if start is None:
        return 0
    end = _to_naive_utc(ended_at) or datetime.now(timezone.utc).replace(tzinfo=None)
    return int(max(0, (end - start).total_seconds()))


async def _ensure_session(db: AsyncSession, user: User, session_id: str, title: str | None = None):
    row = (
        await db.execute(
            select(CommandSession).where(
                CommandSession.id == session_id,
                CommandSession.tenant_id == _tenant_id(user),
            )
        )
    ).scalars().first()
    if row:
        return row
    row = CommandSession(
        id=session_id,
        tenant_id=_tenant_id(user),
        alarm_id=session_id,
        title=title or f"Command session {session_id}",  # i18n
        status="open",
        started_by_user_id=user.id,
    )
    db.add(row)
    await db.flush()
    return row


@router.get("/sessions")
async def list_sessions(
    status: str = Query(""),
    keyword: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    stmt = select(CommandSession).where(CommandSession.tenant_id == _tenant_id(current_user))
    status_filter = (status or "").strip().lower()
    if status_filter and status_filter in {"open", "closed"}:
        stmt = stmt.where(CommandSession.status == status_filter)
    kw = (keyword or "").strip()
    if kw:
        stmt = stmt.where(
            or_(
                CommandSession.id.ilike(f"%{kw}%"),
                CommandSession.title.ilike(f"%{kw}%"),
                CommandSession.alarm_id.ilike(f"%{kw}%"),
            )
        )
    stmt = stmt.order_by(desc(CommandSession.started_at)).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    session_ids = [str(r.id) for r in rows if getattr(r, "id", None)]
    participant_count_map: dict[str, int] = {}
    instruction_count_map: dict[str, int] = {}
    last_instruction_at_map: dict[str, str | None] = {}
    if session_ids:
        part_rows = (
            await db.execute(
                select(CommandParticipant.session_id, func.count(CommandParticipant.id))
                .where(CommandParticipant.session_id.in_(session_ids))
                .group_by(CommandParticipant.session_id)
            )
        ).all()
        participant_count_map = {str(sid): int(cnt or 0) for sid, cnt in part_rows}

        inst_rows = (
            await db.execute(
                select(CommandInstruction.session_id, func.count(CommandInstruction.id))
                .where(CommandInstruction.session_id.in_(session_ids))
                .group_by(CommandInstruction.session_id)
            )
        ).all()
        instruction_count_map = {str(sid): int(cnt or 0) for sid, cnt in inst_rows}
        last_inst_rows = (
            await db.execute(
                select(CommandInstruction.session_id, func.max(CommandInstruction.created_at))
                .where(CommandInstruction.session_id.in_(session_ids))
                .group_by(CommandInstruction.session_id)
            )
        ).all()
        last_instruction_at_map = {str(sid): (ts.isoformat() if ts else None) for sid, ts in last_inst_rows}

    return [
        {
            "id": r.id,
            "alarm_id": r.alarm_id,
            "title": r.title,
            "status": r.status,
            "started_by_user_id": r.started_by_user_id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "summary": r.summary,
            "participant_count": participant_count_map.get(str(r.id), 0),
            "instruction_count": instruction_count_map.get(str(r.id), 0),
            "last_instruction_at": last_instruction_at_map.get(str(r.id)),
            "duration_sec": _duration_sec(r.started_at, r.ended_at),
        }
        for r in rows
    ]


@router.post("/sessions")
async def create_session(
    body: CommandSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    session_id = (body.alarm_id or "").strip() or f"cm_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    existing = (
        await db.execute(
            select(CommandSession).where(
                CommandSession.id == session_id,
                CommandSession.tenant_id == _tenant_id(current_user),
            )
        )
    ).scalars().first()
    if existing:
        await safe_auth_audit(
            db,
            module="command",
            action="create_command_session",
            source="command_console",
            operator=current_user.username or "unknown",
            result="success",
            tenant_id=_audit_tid(current_user),
            status_code=200,
            detail="session_exists",
            extra_summary=f"session_id={existing.id}",
        )
        return {"id": existing.id, "status": existing.status, "title": existing.title}
    row = CommandSession(
        id=session_id,
        tenant_id=_tenant_id(current_user),
        alarm_id=(body.alarm_id or "").strip() or None,
        title=(body.title or "").strip() or f"报警会商 {session_id}",
        status="open",
        started_by_user_id=current_user.id,
    )
    db.add(row)
    db.add(
        CommandParticipant(
            session_id=row.id,
            user_id=current_user.id,
            username=current_user.username,
            role="owner",
        )
    )
    await db.commit()
    await safe_auth_audit(
        db,
        module="command",
        action="create_command_session",
        source="command_console",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=201,
        detail="ok",
        extra_summary=f"session_id={row.id}; alarm_id={row.alarm_id or ''}",
    )
    return {"id": row.id, "status": row.status, "title": row.title}


@router.post("/sessions/{session_id}/join")
async def join_session(
    session_id: str,
    body: CommandSessionJoin,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    session = (
        await db.execute(
            select(CommandSession).where(
                CommandSession.id == session_id,
                CommandSession.tenant_id == _tenant_id(current_user),
            )
        )
    ).scalars().first()
    if not session:
        await safe_auth_audit(
            db,
            module="command",
            action="join_command_session",
            source="command_console",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="session_not_found",
            extra_summary=f"session_id={session_id}",
        )
        raise HTTPException(status_code=404, detail="Talk session not found")
    exists = (
        await db.execute(
            select(CommandParticipant).where(
                CommandParticipant.session_id == session_id,
                CommandParticipant.user_id == current_user.id,
            )
        )
    ).scalars().first()
    if not exists:
        db.add(
            CommandParticipant(
                session_id=session_id,
                user_id=current_user.id,
                username=current_user.username,
                role=(body.role or "participant")[:24],
            )
        )
        await db.commit()
    joined_new = not exists
    await safe_auth_audit(
        db,
        module="command",
        action="join_command_session",
        source="command_console",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"session_id={session_id}; joined_new={joined_new}; role={(body.role or 'participant')[:24]}",
    )
    return {"ok": True, "session_id": session_id}


@router.get("/sessions/{session_id}/participants")
async def list_participants(
    session_id: str,
    role: str = Query("", description="按成员角色过滤: owner/participant/coordinator/observer"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    session = (
        await db.execute(
            select(CommandSession).where(
                CommandSession.id == session_id,
                CommandSession.tenant_id == _tenant_id(current_user),
            )
        )
    ).scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Talk session not found")
    stmt = select(CommandParticipant).where(CommandParticipant.session_id == session_id)
    role_filter = (role or "").strip().lower()
    if role_filter:
        stmt = stmt.where(CommandParticipant.role == role_filter)
    rows = (await db.execute(stmt.order_by(desc(CommandParticipant.joined_at)))).scalars().all()
    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "user_id": r.user_id,
            "username": r.username,
            "role": r.role,
            "joined_at": r.joined_at.isoformat() if r.joined_at else None,
        }
        for r in rows
    ]


@router.post("/sessions/{session_id}/close")
async def close_session(
    session_id: str,
    body: CommandSessionClose,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    session = (
        await db.execute(
            select(CommandSession).where(
                CommandSession.id == session_id,
                CommandSession.tenant_id == _tenant_id(current_user),
            )
        )
    ).scalars().first()
    if not session:
        await safe_auth_audit(
            db,
            module="command",
            action="close_command_session",
            source="command_console",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="session_not_found",
            extra_summary=f"session_id={session_id}",
        )
        raise HTTPException(status_code=404, detail="Talk session not found")
    session.status = "closed"
    session.summary = (body.summary or "").strip() or session.summary
    session.ended_at = datetime.now(timezone.utc)
    await db.commit()
    await safe_auth_audit(
        db,
        module="command",
        action="close_command_session",
        source="command_console",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"session_id={session_id}; status={session.status}",
    )
    return {"ok": True, "session_id": session_id, "status": session.status}


@router.get("/instructions")
async def list_instructions(
    session_id: str = Query(..., description="会商会话ID，一般为 alarm_id"),
    keyword: str = Query("", description="按指令内容关键字过滤"),
    since_at: Optional[datetime] = Query(None, description="仅返回该时间之后的新指令（ISO8601）"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    await _ensure_session(db, current_user, session_id)
    stmt = select(CommandInstruction).where(CommandInstruction.session_id == session_id)
    kw = (keyword or "").strip()
    if kw:
        stmt = stmt.where(CommandInstruction.content.ilike(f"%{kw}%"))
    if since_at:
        stmt = stmt.where(CommandInstruction.created_at > since_at)
    stmt = stmt.order_by(desc(CommandInstruction.created_at)).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "content": r.content,
            "user_id": r.user_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/instructions")
async def create_instruction(
    body: CommandInstructionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    session_id = body.session_id.strip()
    if not session_id:
        await safe_auth_audit(
            db,
            module="command",
            action="create_command_instruction",
            source="command_console",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="session_id_required",
        )
        raise HTTPException(status_code=400, detail="session_id cannot be empty")
    await _ensure_session(db, current_user, session_id)
    row = CommandInstruction(
        session_id=session_id,
        content=body.content.strip(),
        user_id=current_user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    content_hint = (row.content or "").replace(";", ".").replace("\n", " ")[:80]
    await safe_auth_audit(
        db,
        module="command",
        action="create_command_instruction",
        source="command_console",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=201,
        detail="ok",
        extra_summary=f"instruction_id={row.id}; session_id={row.session_id}; content_hint={content_hint}",
    )
    return {
        "id": row.id,
        "session_id": row.session_id,
        "content": row.content,
        "user_id": row.user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
