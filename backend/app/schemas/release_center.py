from datetime import datetime
from pydantic import BaseModel, Field


class DiffItem(BaseModel):
    module: str
    path: str
    before: str | int | float | bool | None = None
    after: str | int | float | bool | None = None
    risk_level: str = "low"


class DiffResponse(BaseModel):
    from_revision: int
    to_draft: str
    changes: list[DiffItem] = Field(default_factory=list)


class PublishRequest(BaseModel):
    draft_id: str
    confirm_token: str  # 凭证痕迹 — 移除默认值"publish-confirmed"，必须由调用方显式传入
    publish_note: str | None = None


class PublishResponse(BaseModel):
    publish_id: str
    revision: int
    status: str
    published_at: datetime


class RollbackRequest(BaseModel):
    target_revision: int
    reason: str | None = None


# 补充 rollback 的 response_model，使接口返回类型明确
class RollbackResponse(BaseModel):
    status: str
    target_revision: int
