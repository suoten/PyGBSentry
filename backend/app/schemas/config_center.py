from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class DraftResponse(BaseModel):
    draft_id: str
    base_revision: int
    status: str
    modules: dict = Field(default_factory=dict)
    updated_at: datetime


class UpdateDraftModuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload: dict = Field(default_factory=dict)
    operator: str | None = None


class ValidationIssue(BaseModel):
    field: str
    message: str


class ValidateDraftResponse(BaseModel):
    valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    # FIX: [2026-08-22 P1] 原声明 list[str]，但 config_validator_service 对嵌套模块
    # 产生的 hints 为 {"field","message"} dict 列表（与 errors/warnings 同构），
    # pydantic 无法将 dict 校验为 str → ResponseValidationError → 接口 500。
    # 修正为 list[ValidationIssue]，与 service 实际返回结构一致。
    hints: list[ValidationIssue] = Field(default_factory=list)
