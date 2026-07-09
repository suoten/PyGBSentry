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
    hints: list[str] = Field(default_factory=list)
