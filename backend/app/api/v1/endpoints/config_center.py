from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.models.system_setting import SystemSetting
from app.schemas.config_center import DraftResponse, UpdateDraftModuleRequest, ValidateDraftResponse
from app.services.config_center_service import config_center_service
from app.services.auth_audit import safe_auth_audit
from pydantic import BaseModel, ConfigDict, Field, AliasChoices
from typing import Optional, Literal
import json
from loguru import logger

router = APIRouter()

def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"

BASIC_CONFIG_KEY = "config_basic"


class BasicConfigPayload(BaseModel):
    # FIX [2026-09-01 P1]: GET 返回与前端提交均使用 camelCase（pluginSandboxCpuLimitPercent），
    # 原字段为 snake_case 且 extra="forbid"，导致基础配置保存必然 400
    # （Parameter 'pluginSandboxCpuLimitPercent' validation failed）。
    # 通过 validation_alias 同时兼容两种命名。
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    streamPullTimeout: Optional[int] = Field(None, ge=1, le=300)
    alarmDefaultLevel: Optional[Literal["low", "medium", "high"]] = None
    deviceHeartbeatInterval: Optional[int] = Field(None, ge=5, le=600)
    recordAutoCleanDays: Optional[int] = Field(None, ge=0, le=365)
    logRetentionDays: Optional[int] = Field(None, ge=1, le=365)
    plugin_sandbox_cpu_limit_percent: Optional[int] = Field(
        None,
        ge=0,
        le=100,
        validation_alias=AliasChoices("pluginSandboxCpuLimitPercent", "plugin_sandbox_cpu_limit_percent"),
    )
    plugin_sandbox_memory_limit_mb: Optional[int] = Field(
        None,
        ge=0,
        validation_alias=AliasChoices("pluginSandboxMemoryLimitMb", "plugin_sandbox_memory_limit_mb"),
    )
    plugin_sandbox_disk_limit_mb: Optional[int] = Field(
        None,
        ge=0,
        validation_alias=AliasChoices("pluginSandboxDiskLimitMb", "plugin_sandbox_disk_limit_mb"),
    )


@router.get("/basic")
async def get_basic_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    r = (await db.execute(select(SystemSetting).where(SystemSetting.setting_key == BASIC_CONFIG_KEY))).scalars().first()
    if not r or not (r.setting_value or "").strip():
        return {
            "streamPullTimeout": 10,
            "alarmDefaultLevel": "medium",
            "deviceHeartbeatInterval": 60,
            "recordAutoCleanDays": 0,
            "logRetentionDays": 7,
        }
    try:
        data = json.loads(r.setting_value)
    except Exception:
        logger.warning("Failed to parse basic config JSON, using defaults")
        data = {}
    return {
        "streamPullTimeout": data.get("streamPullTimeout", 10),
        "alarmDefaultLevel": data.get("alarmDefaultLevel", "medium"),
        "deviceHeartbeatInterval": data.get("deviceHeartbeatInterval", 60),
        "recordAutoCleanDays": data.get("recordAutoCleanDays", 0),
        "logRetentionDays": data.get("logRetentionDays", 7),
        "pluginSandboxCpuLimitPercent": data.get("pluginSandboxCpuLimitPercent", None),
        "pluginSandboxMemoryLimitMb": data.get("pluginSandboxMemoryLimitMb", None),
        "pluginSandboxDiskLimitMb": data.get("pluginSandboxDiskLimitMb", None),
    }


@router.put("/basic")
async def update_basic_config(
    payload: BasicConfigPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    r = (await db.execute(select(SystemSetting).where(SystemSetting.setting_key == BASIC_CONFIG_KEY))).scalars().first()
    existing: dict = {}
    if r and (r.setting_value or "").strip():
        try:
            existing = json.loads(r.setting_value)
        except Exception:
            logger.warning("Failed to parse existing basic config JSON on update")
            existing = {}
    if payload.streamPullTimeout is not None:
        existing["streamPullTimeout"] = payload.streamPullTimeout
    if payload.alarmDefaultLevel is not None:
        existing["alarmDefaultLevel"] = payload.alarmDefaultLevel
    if payload.deviceHeartbeatInterval is not None:
        existing["deviceHeartbeatInterval"] = payload.deviceHeartbeatInterval
    if payload.recordAutoCleanDays is not None:
        existing["recordAutoCleanDays"] = payload.recordAutoCleanDays
    if payload.logRetentionDays is not None:
        existing["logRetentionDays"] = payload.logRetentionDays
    if payload.plugin_sandbox_cpu_limit_percent is not None:
        existing["pluginSandboxCpuLimitPercent"] = payload.plugin_sandbox_cpu_limit_percent
    if payload.plugin_sandbox_memory_limit_mb is not None:
        existing["pluginSandboxMemoryLimitMb"] = payload.plugin_sandbox_memory_limit_mb
    if payload.plugin_sandbox_disk_limit_mb is not None:
        existing["pluginSandboxDiskLimitMb"] = payload.plugin_sandbox_disk_limit_mb
    value = json.dumps(existing, ensure_ascii=False)
    if r:
        r.setting_value = value
    else:
        db.add(SystemSetting(setting_key=BASIC_CONFIG_KEY, setting_value=value))
    await db.commit()
    await safe_auth_audit(
        db,
        module="config-center",
        action="update_basic_config",
        source="config_center",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"keys_updated={[k for k, v in payload.dict().items() if v is not None]}",
    )
    return existing


@router.get("/drafts/current", response_model=DraftResponse)
async def get_current_draft(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    return await config_center_service.get_or_create_current_draft(db)


@router.put("/drafts/{draft_id}/modules/{module_name}", response_model=DraftResponse)
async def update_draft_module(
    draft_id: str,
    module_name: str,
    payload: UpdateDraftModuleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    operator = payload.operator or current_user.username
    try:
        return await config_center_service.update_draft_module(
            db=db,
            draft_id=draft_id,
            module_name=module_name,
            payload=payload.payload,
            operator=operator,
        )
    except Exception as e:
        await safe_auth_audit(
            db,
            module="config-center",
            action="update_draft_module",
            source="config_center",
            operator=operator or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=500,
            detail="update_draft_module_exception",
            extra_summary=f"draft_id={draft_id}; module_name={module_name}; err={str(e)[:200]}",
        )
        raise


@router.post("/drafts/{draft_id}/validate", response_model=ValidateDraftResponse)
async def validate_draft(
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    return await config_center_service.validate_draft(db, draft_id, current_user.username)
