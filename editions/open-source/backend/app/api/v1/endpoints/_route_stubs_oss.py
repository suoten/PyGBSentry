"""
路由桩（oss版）— 企业版专有功能的占位端点。
所有路由返回 501 Not Implemented + deprecated 标记。
已由真实实现覆盖的 stub 已移除，仅保留企业版专有功能占位。
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["stubs"])


async def _stub(path: str, method: str, note: str = ""):
    raise HTTPException(status_code=501, detail=f"Endpoint not implemented: {method} {path} {note}")  # FIXED: 中文→英文


@router.post("/login/admin/access-token", deprecated=True)
async def stub_post_login_admin_access_token():
    """[STUB] 企业版: 管理员令牌 — POST /login/admin/access-token"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.post("/login/developer/access-token", deprecated=True)
async def stub_post_login_developer_access_token():
    """[STUB] 企业版: 开发者令牌 — POST /login/developer/access-token"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.post("/login/tenant/access-token", deprecated=True)
async def stub_post_login_tenant_access_token():
    """[STUB] 企业版: 租户令牌 — POST /login/tenant/access-token"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.post("/plugins/marketplace/{id}/official-publish", deprecated=True)
async def stub_post_plugins_marketplace_id_official_publish():
    """[STUB] 企业版: 官方发布 — POST /plugins/marketplace/{id}/official-publish"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.put("/ops/help-docs/{id}", deprecated=True)
async def stub_put_ops_help_docs_id():
    """[STUB] 企业版: 帮助文档更新 — PUT /ops/help-docs/{id}"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.post("/ops/help-docs", deprecated=True)
async def stub_post_ops_help_docs():
    """[STUB] 企业版: 帮助文档创建 — POST /ops/help-docs"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.delete("/ops/help-docs/{id}", deprecated=True)
async def stub_delete_ops_help_docs_id():
    """[STUB] 企业版: 帮助文档删除 — DELETE /ops/help-docs/{id}"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/plugins/config/menus/{id}", deprecated=True)
async def stub_get_plugins_config_menus_id():
    """[STUB] 企业版: 插件菜单配置 — GET /plugins/config/menus/{id}"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.post("/plugins/config/menus/{id}", deprecated=True)
async def stub_post_plugins_config_menus_id():
    """[STUB] 企业版: 插件菜单配置 — POST /plugins/config/menus/{id}"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/plugins/config/schema/{id}", deprecated=True)
async def stub_get_plugins_config_schema_id():
    """[STUB] 企业版: 插件配置 Schema — GET /plugins/config/schema/{id}"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.post("/plugins/config/schema/{id}", deprecated=True)
async def stub_post_plugins_config_schema_id():
    """[STUB] 企业版: 插件配置 Schema — POST /plugins/config/schema/{id}"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/plugins/config/{id}/values", deprecated=True)
async def stub_get_plugins_config_id_values():
    """[STUB] 企业版: 插件配置值 — GET /plugins/config/{id}/values"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.put("/plugins/config/{id}/values", deprecated=True)
async def stub_put_plugins_config_id_values():
    """[STUB] 企业版: 插件配置值更新 — PUT /plugins/config/{id}/values"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/plugins/config/{id}/history", deprecated=True)
async def stub_get_plugins_config_id_history():
    """[STUB] 企业版: 插件配置历史 — GET /plugins/config/{id}/history"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.post("/plugins/auto-assign", deprecated=True)
async def stub_post_plugins_auto_assign():
    """[STUB] 企业版: 插件自动分配 — POST /plugins/auto-assign"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/plugins/marketplace/{id}/rollout", deprecated=True)
async def stub_get_plugins_marketplace_id_rollout():
    """[STUB] 企业版: 灰度发布 — GET /plugins/marketplace/{id}/rollout"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/plugins/marketplace/{id}/rollout/whitelist", deprecated=True)
async def stub_get_plugins_marketplace_id_rollout_whitelist():
    """[STUB] 企业版: 灰度白名单 — GET /plugins/marketplace/{id}/rollout/whitelist"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.put("/plugins/marketplace/{id}/rollout", deprecated=True)
async def stub_put_plugins_marketplace_id_rollout():
    """[STUB] 企业版: 灰度发布更新 — PUT /plugins/marketplace/{id}/rollout"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.post("/plugins/marketplace/{id}/rollout/whitelist", deprecated=True)
async def stub_post_plugins_marketplace_id_rollout_whitelist():
    """[STUB] 企业版: 灰度白名单添加 — POST /plugins/marketplace/{id}/rollout/whitelist"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.delete("/plugins/marketplace/{id}/rollout/whitelist", deprecated=True)
async def stub_delete_plugins_marketplace_id_rollout_whitelist():
    """[STUB] 企业版: 灰度白名单删除 — DELETE /plugins/marketplace/{id}/rollout/whitelist"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/plugins/license/signing-key-rotation/state", deprecated=True)
async def stub_get_plugins_license_signing_key_rotation_state():
    """[STUB] 企业版: 签名密钥轮换状态 — GET /plugins/license/signing-key-rotation/state"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/plugins/license/signing-key-rotation/records", deprecated=True)
async def stub_get_plugins_license_signing_key_rotation_records():
    """[STUB] 企业版: 签名密钥轮换记录 — GET /plugins/license/signing-key-rotation/records"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.post("/plugins/license/signing-key-rotation/plan", deprecated=True)
async def stub_post_plugins_license_signing_key_rotation_plan():
    """[STUB] 企业版: 签名密钥轮换计划 — POST /plugins/license/signing-key-rotation/plan"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.post("/plugins/license/signing-key-rotation/execute", deprecated=True)
async def stub_post_plugins_license_signing_key_rotation_execute():
    """[STUB] 企业版: 签名密钥轮换执行 — POST /plugins/license/signing-key-rotation/execute"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.post("/plugins/license/signing-key-rotation/rollback", deprecated=True)
async def stub_post_plugins_license_signing_key_rotation_rollback():
    """[STUB] 企业版: 签名密钥轮换回滚 — POST /plugins/license/signing-key-rotation/rollback"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/system/slo/metrics", deprecated=True)
async def stub_get_system_slo_metrics():
    """[STUB] 企业版: SLO 指标 — GET /system/slo/metrics"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/plugins/marketplace/revenue-config", deprecated=True)
async def stub_get_plugins_marketplace_revenue_config():
    """[STUB] 企业版: 收入配置 — GET /plugins/marketplace/revenue-config"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/users/me/developer-workspace", deprecated=True)
async def stub_get_users_me_developer_workspace():
    """[STUB] 企业版: 开发者工作区 — GET /users/me/developer-workspace"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.patch("/users/me/developer-workspace", deprecated=True)
async def stub_patch_users_me_developer_workspace():
    """[STUB] 企业版: 更新开发者工作区 — PATCH /users/me/developer-workspace"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.post("/users/me/agreements", deprecated=True)
async def stub_post_users_me_agreements():
    """[STUB] 企业版: 用户协议签署 — POST /users/me/agreements"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/plugins/marketplace/api-keys", deprecated=True)
async def stub_get_plugins_marketplace_api_keys():
    """[STUB] 企业版: 市场 API 密钥 — GET /plugins/marketplace/api-keys"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.post("/plugins/marketplace/api-keys", deprecated=True)
async def stub_post_plugins_marketplace_api_keys():
    """[STUB] 企业版: 创建市场 API 密钥 — POST /plugins/marketplace/api-keys"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.delete("/plugins/marketplace/api-keys/{id}", deprecated=True)
async def stub_delete_plugins_marketplace_api_keys_id():
    """[STUB] 企业版: 删除市场 API 密钥 — DELETE /plugins/marketplace/api-keys/{id}"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/plugins/my", deprecated=True)
async def stub_get_plugins_my():
    """[STUB] 企业版: 我的插件 — GET /plugins/my"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/plugins/marketplace/submissions/me", deprecated=True)
async def stub_get_plugins_marketplace_submissions_me():
    """[STUB] 企业版: 我的提交 — GET /plugins/marketplace/submissions/me"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.post("/plugins/marketplace/validate-upload", deprecated=True)
async def stub_post_plugins_marketplace_validate_upload():
    """[STUB] 企业版: 验证上传包 — POST /plugins/marketplace/validate-upload"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.post("/plugins/marketplace/submissions", deprecated=True)
async def stub_post_plugins_marketplace_submissions():
    """[STUB] 企业版: 提交插件 — POST /plugins/marketplace/submissions"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/plugins/marketplace/public/{id}", deprecated=True)
async def stub_get_plugins_marketplace_public_id():
    """[STUB] 企业版: 公开插件详情 — GET /plugins/marketplace/public/{id}"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/plugins/webhooks", deprecated=True)
async def stub_get_plugins_webhooks():
    """[STUB] 企业版: Webhook 列表 — GET /plugins/webhooks"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/plugins/webhooks/events", deprecated=True)
async def stub_get_plugins_webhooks_events():
    """[STUB] 企业版: Webhook 事件 — GET /plugins/webhooks/events"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.post("/plugins/webhooks", deprecated=True)
async def stub_post_plugins_webhooks():
    """[STUB] 企业版: 创建 Webhook — POST /plugins/webhooks"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.delete("/plugins/webhooks/{id}", deprecated=True)
async def stub_delete_plugins_webhooks_id():
    """[STUB] 企业版: 删除 Webhook — DELETE /plugins/webhooks/{id}"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文


@router.get("/audit-center/export.pdf", deprecated=True)
async def stub_get_audit_center_export_pdf():
    """[STUB] 企业版: PDF 审计导出 — GET /audit-center/export.pdf"""
    raise HTTPException(status_code=501, detail="Enterprise-only endpoint, not implemented in open-source edition")  # FIXED: 中文→英文
