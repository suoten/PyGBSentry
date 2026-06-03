from fastapi import APIRouter, Depends, HTTPException
from app.api import deps
from app.models.user import User
from app.schemas.ssl_cert import CertStatusResponse, CertRenewRequest, CertRenewResponse
from app.services.ssl_certbot.certbot_manager import get_status, force_renew
from app.services.ssl_certbot.certbot_config import load_certbot_settings

router = APIRouter()


@router.get("/status", response_model=CertStatusResponse)
async def cert_status(
    current_user: User = Depends(deps.require_roles(["admin"])),
):
    try:
        cfg = load_certbot_settings()
        if not cfg.is_effective:
            return CertStatusResponse(enabled=False, domain=cfg.domain, status="disabled")
        cert_info = await get_status()
        return CertStatusResponse(
            enabled=True,
            domain=cert_info.domain,
            status=str(cert_info.status),
            not_before=cert_info.not_before,
            not_after=cert_info.not_after,
            remaining_days=cert_info.remaining_days,
            cert_path=cert_info.cert_path,
            last_renew_at=cert_info.last_renew_at,
            last_check_at=cert_info.last_check_at,
            error=cert_info.error,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SSL cert status check failed: {str(e)}") from e  # FIXED: 异常保护


@router.post("/renew", response_model=CertRenewResponse)
async def cert_renew(
    request: CertRenewRequest = CertRenewRequest(),
    current_user: User = Depends(deps.require_roles(["admin"])),
):
    try:
        success, message = await force_renew()
        return CertRenewResponse(success=success, message=message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SSL cert renewal failed: {str(e)}") from e  # FIXED: 异常保护
