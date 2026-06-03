"""
plugins_license — 插件 License 校验相关端点。
"""

from fastapi import APIRouter, Depends

from app.api import deps
from app.models.user import User
from app.services.license_service import (
    verify_license_payload,
    sign_license_payload,
    generate_ed25519_keypair,
)

from .plugins_common import (
    LicenseVerifyRequest,
    LicenseSignRequest,
)

router = APIRouter()


@router.post("/license/verify")
async def verify_license(
    payload: LicenseVerifyRequest,
    current_user: User = Depends(deps.get_current_active_superuser),
):
    """验证插件 License 是否有效（超管）。"""
    valid, reason = verify_license_payload(
        license_data=payload.license_data,
        tenant_id=payload.tenant_id,
        plugin_id=payload.plugin_id,
        feature_code=payload.feature_code,
    )
    return {"valid": valid, "reason": reason}


@router.post("/license/sign")
async def sign_license(
    payload: LicenseSignRequest,
    current_user: User = Depends(deps.get_current_active_superuser),
):
    """签名插件 License（超管，用于开发/测试）。"""
    signed = sign_license_payload(payload.license_data)
    return signed


@router.get("/license/keypair")
async def generate_keypair(
    current_user: User = Depends(deps.get_current_active_superuser),
):
    """生成 Ed25519 密钥对（超管，用于初始化签名环境）。"""
    keypair = generate_ed25519_keypair()
    return keypair
