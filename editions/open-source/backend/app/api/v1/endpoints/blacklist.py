from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.db.session import get_db
from app.models.ip_blacklist import IpBlacklist
from app.models.user import User
from app.api import deps
from app.services.auth_audit import safe_auth_audit
import asyncio

router = APIRouter()


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"

@router.get("")
async def get_blacklists(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    stmt = select(IpBlacklist)
    res = await db.execute(stmt)
    items = res.scalars().all()
    return [{"ip": i.ip, "reason": i.reason, "created_at": i.created_at} for i in items]

@router.delete("/{ip}")
async def remove_blacklist(
    ip: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    stmt = delete(IpBlacklist).where(IpBlacklist.ip == ip)
    result = await db.execute(stmt)
    await db.commit()
    rc = getattr(result, "rowcount", None) or 0
    if rc > 0:
        await safe_auth_audit(
            db,
            module="blacklist",
            action="remove_ip",
            source="ip_blacklist",
            operator=current_user.username or "unknown",
            result="success",
            tenant_id=_audit_tid(current_user),
            status_code=200,
            detail="ok",
            extra_summary=f"ip={ip}",
        )
    else:
        await safe_auth_audit(
            db,
            module="blacklist",
            action="remove_ip",
            source="ip_blacklist",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="ip_not_in_list",
            extra_summary=f"ip={ip}",
        )

    if rc > 0:
        from app.sip.server import sip_server

        if hasattr(sip_server, "reload_ip_blacklist"):
            async def _reload_with_catch():
                try:
                    await sip_server.reload_ip_blacklist()
                except Exception as e:
                    from loguru import logger
                    logger.warning(f"reload_ip_blacklist failed: {e}")
            asyncio.create_task(_reload_with_catch())

    return {"message": "Success"}
