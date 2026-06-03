from datetime import datetime
from pydantic import BaseModel


class CertStatusResponse(BaseModel):
    enabled: bool = False
    domain: str = ""
    status: str = "disabled"
    not_before: datetime | None = None
    not_after: datetime | None = None
    remaining_days: int = 0
    cert_path: str = ""
    last_renew_at: datetime | None = None
    last_check_at: datetime | None = None
    error: str = ""


class CertRenewRequest(BaseModel):
    force: bool = False


class CertRenewResponse(BaseModel):
    success: bool
    message: str
