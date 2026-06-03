from datetime import datetime
from pydantic import BaseModel, Field


class AuditLogItem(BaseModel):
    audit_id: str
    module: str
    action: str
    operator: str
    result: str
    summary: str
    plugin_id: str | None = None
    source: str | None = None
    tenant_id: str | None = None
    status_code: int | None = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    total: int
    items: list[AuditLogItem] = Field(default_factory=list)


class AuditStatsActionItem(BaseModel):
    name: str
    count: int


class AuditStatsCodeItem(BaseModel):
    code: str
    count: int


class AuditStatsResponse(BaseModel):
    total: int
    failed: int
    top_actions: list[AuditStatsActionItem] = Field(default_factory=list)
    top_status_codes: list[AuditStatsCodeItem] = Field(default_factory=list)
    status_buckets: dict[str, int] = Field(default_factory=dict)
