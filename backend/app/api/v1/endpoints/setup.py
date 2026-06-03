"""首次部署安装向导：状态查询与完成标记（开源版）"""
import os
from app.core.http_client import get_http_client
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.session import AsyncSessionLocal, get_db
from app.api import deps
from app.models.user import User
from loguru import logger  # 添加logger导入
from app.services.auth_audit import safe_auth_audit

router = APIRouter()

# 向导完成标记文件（放在 backend 运行目录下 data/.wizard_completed）
def _wizard_state_dir():
    return os.path.join(os.getcwd(), "data")

def _wizard_done_path():
    return os.path.join(_wizard_state_dir(), ".wizard_completed")

def _is_wizard_completed() -> bool:
    path = _wizard_done_path()
    return os.path.isfile(path)

def _set_wizard_completed():
    d = _wizard_state_dir()
    try:
        os.makedirs(d, exist_ok=True)
        with open(_wizard_done_path(), "w") as f:
            f.write("1")
    except (OSError, IOError) as e:
        logger.warning("Failed to write setup wizard done marker: %s", e)  # 异常吞没→日志记录

@router.get("/status")
async def get_setup_status(current_user: User = Depends(deps.require_roles(["owner", "admin"]))):
    """
    安装向导状态与连通性检测。返回：是否已完成向导、数据库是否正常、ZLM 是否可达。
    """
    wizard_completed = _is_wizard_completed()
    db_ok = False
    db_detail = ""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        db_detail = str(e)

    zlm_ok = False
    zlm_detail = ""
    try:
        res = await (await get_http_client()).get(
            f"http://{settings.MEDIA_SERVER_HOST}:{settings.MEDIA_SERVER_HTTP_PORT}/index/api/getServerConfig?secret={settings.MEDIA_SERVER_SECRET}",
            timeout=3,
        )
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == 0:
                zlm_ok = True
            else:
                zlm_detail = "ZLM returned an error"
        else:
            zlm_detail = f"HTTP {res.status_code}"
    except Exception:
        zlm_detail = "Connection failed"

    return {
        "wizard_completed": wizard_completed,
        "db_ok": db_ok,
        "db_detail": db_detail or None,
        "zlm_ok": zlm_ok,
        "zlm_detail": zlm_detail or None,
    }


@router.post("/complete")
async def complete_setup(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    """标记安装向导已完成（仅需执行一次）。"""
    if _is_wizard_completed():
        return {"status": "ok", "message": "Setup wizard completed"}  # i18n
    _set_wizard_completed()
    tid = (current_user.tenant_id or "default").strip() or "default"
    await safe_auth_audit(
        db,
        module="setup",
        action="wizard_complete",
        source="setup_wizard",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=tid,
        status_code=200,
        detail="ok",
        extra_summary=f"user_id={current_user.id}",
    )
    return {"status": "ok", "message": "Installation wizard completed"}  # i18n
