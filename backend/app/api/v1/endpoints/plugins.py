"""FIXED: [2026-07-10] P-01/P-02 OSS 版插件中心端点模块 [全栈工程师]

打通"官网购买→OSS 下载安装→license 在线校验"完整链路：
- 本地端点：已安装列表、健康状态、安全报告、上传安装、卸载预览、卸载
- 市场代理端点：市场列表、商店 URL、已购列表、购买、确认、市场安装

市场代理端点将请求转发到 PLUGIN_MARKETPLACE_SERVER_URL（官网），携带 OSS 实例认证头。
本地端点直接操作 plugin_manager 单例。
"""
import os
import json
import tempfile
import shutil
from typing import Any

import aiohttp
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request, Form
from loguru import logger

from app.api import deps
from app.core.config import settings
from app.core.plugin_manager import plugin_manager

router = APIRouter()


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _server_base_url() -> str:
    """获取官网市场服务器 URL"""
    url = getattr(settings, "PLUGIN_MARKETPLACE_SERVER_URL", None) or ""
    if not url:
        url = getattr(settings, "PLUGIN_MARKETPLACE_BASE_URL", None) or ""
    return url.strip()


def _instance_headers(body_bytes: bytes = b"") -> dict:
    """获取 OSS 实例认证头（HMAC 签名）"""
    return plugin_manager.get_oss_instance_headers(body_bytes)


def _forward_auth_headers(request: Request) -> dict:
    """从原始请求中提取 Authorization 头转发给官网"""
    headers = {}
    auth = request.headers.get("Authorization", "")
    if auth:
        headers["Authorization"] = auth
    return headers


async def _proxy_to_server(
    method: str,
    path: str,
    request: Request,
    *,
    json_body: dict | None = None,
    params: dict | None = None,
) -> Any:
    """将请求代理到官网市场服务器，携带 OSS 实例认证 + 用户认证"""
    base = _server_base_url()
    if not base:
        raise HTTPException(status_code=503, detail="Plugin marketplace server not configured")
    url = f"{base.rstrip('/')}/api/v1{path}"

    body_bytes = json.dumps(json_body).encode("utf-8") if json_body else b""
    headers = {
        "Content-Type": "application/json",
        **_instance_headers(body_bytes),
        **_forward_auth_headers(request),
    }

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method, url, data=body_bytes if body_bytes else None,
                headers=headers, params=params,
            ) as resp:
                resp_data = await resp.json()
                if resp.status >= 400:
                    detail = resp_data.get("detail") or resp_data.get("message") or f"Server returned {resp.status}"
                    raise HTTPException(status_code=resp.status, detail=str(detail)[:500])
                return resp_data
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Plugin marketplace proxy error: {method} {path}: {e}")
        raise HTTPException(status_code=502, detail=f"Marketplace server unreachable: {str(e)[:200]}")


# ---------------------------------------------------------------------------
# 本地端点 — 直接操作 plugin_manager
# ---------------------------------------------------------------------------

@router.get("/installed")
async def list_installed_plugins(
    current_user=Depends(deps.get_current_active_user),
):
    """列出已安装插件"""
    items = []
    for pid, meta in plugin_manager.metadata.items():
        if not isinstance(meta, dict):
            continue
        items.append({
            "id": pid,
            "name": meta.get("name", pid),
            "version": meta.get("version", ""),
            "description": meta.get("description", ""),
            "type": meta.get("type", "free"),
            "author": meta.get("author", ""),
            "enabled": meta.get("enabled", True),
            "entry_point": meta.get("entry_point", ""),
        })
    return items


@router.get("/runtime/health-status")
async def plugins_health_status(
    current_user=Depends(deps.get_current_active_user),
):
    """插件运行时健康状态"""
    health_map = getattr(plugin_manager, "_plugin_health", {}) or {}
    items = []
    for pid, meta in plugin_manager.metadata.items():
        h = health_map.get(pid, {}) if isinstance(health_map, dict) else {}
        items.append({
            "plugin_id": pid,
            "name": (meta or {}).get("name", pid),
            "errors": h.get("errors", 0),
            "restarts": h.get("restarts", 0),
            "disabled": h.get("disabled", False),
            "status": "disabled" if h.get("disabled") else ("error" if h.get("errors", 0) > 0 else "ok"),
        })
    return {"items": items}


@router.get("/runtime/security-report")
async def plugins_security_report(
    current_user=Depends(deps.get_current_active_user),
):
    """插件运行时安全报告"""
    items = []
    for pid, meta in plugin_manager.metadata.items():
        if not isinstance(meta, dict):
            continue
        items.append({
            "plugin_id": pid,
            "name": meta.get("name", pid),
            "type": meta.get("type", "free"),
            "license_verified": pid not in plugin_manager._paid_license_last_ok or plugin_manager._paid_license_last_ok.get(pid, True),
            "sandbox_enabled": bool(getattr(settings, "PLUGIN_SANDBOX_RUNTIME_API_BLOCK_ENABLED", True)),
        })
    return {"items": items}


@router.post("/upload")
async def upload_plugin(
    file: UploadFile = File(...),
    sha256: str = Form(None),
    signature: str = Form(None),
    current_user=Depends(deps.get_current_active_user),
):
    """上传插件 zip 包并安装（需 admin/owner 权限）

    可选表单参数：
    - sha256: 插件包 SHA256（用于完整性校验，从官网下载页面获取）
    - signature: 插件包 ed25519 签名（用于验签，从官网下载页面获取）
    """
    # 权限校验
    user_role = str(getattr(current_user, "role", "") or "").lower()
    if user_role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Only admin/owner can install plugins")

    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip plugin packages are accepted")

    # 保存到临时文件
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="plugin_upload_")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            shutil.copyfileobj(file.file, f)

        result = plugin_manager.install_plugin_from_zip(
            tmp_path,
            tenant_id=str(getattr(current_user, "tenant_id", "default") or "default"),
            expected_sha256=(sha256 or None),
            expected_package_signature=(signature or None),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)[:500])
    except Exception as e:
        logger.error(f"Plugin upload install failed: {e}")
        raise HTTPException(status_code=500, detail=f"Plugin install failed: {str(e)[:200]}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError as e:
            # finally 中临时文件清理失败不应掩盖主流程异常，但需保留 debug 痕迹以便排查
            logger.debug(f"Temp file cleanup failed for {tmp_path}: {e}")


@router.get("/{plugin_id}/uninstall-preview")
async def uninstall_preview(
    plugin_id: str,
    current_user=Depends(deps.get_current_active_user),
):
    """预览插件卸载影响"""
    pid = str(plugin_id or "").strip()
    if pid not in plugin_manager.metadata:
        raise HTTPException(status_code=404, detail=f"Plugin {pid} not installed")

    meta = plugin_manager.metadata.get(pid, {}) or {}
    tables = []
    if isinstance(meta.get("tables"), list):
        tables = [str(t) for t in meta["tables"]]

    return {
        "plugin_id": pid,
        "name": meta.get("name", pid),
        "version": meta.get("version", ""),
        "tables": tables,
        "has_config": bool(meta.get("config_template")),
    }


@router.delete("/{plugin_id}")
async def uninstall_plugin(
    plugin_id: str,
    current_user=Depends(deps.get_current_active_user),
):
    """卸载插件（需 admin/owner 权限）"""
    user_role = str(getattr(current_user, "role", "") or "").lower()
    if user_role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Only admin/owner can uninstall plugins")

    try:
        result = plugin_manager.uninstall_plugin(plugin_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)[:500])
    except Exception as e:
        logger.error(f"Plugin uninstall failed: {e}")
        raise HTTPException(status_code=500, detail=f"Plugin uninstall failed: {str(e)[:200]}")


# ---------------------------------------------------------------------------
# 市场代理端点 — 转发到官网市场服务器
# ---------------------------------------------------------------------------

@router.get("/marketplace-shop-url")
async def marketplace_shop_url(
    current_user=Depends(deps.get_current_active_user),
):
    """返回官网市场商店 URL（供前端跳转）"""
    url = _server_base_url()
    return {"url": f"{url.rstrip('/')}/portal/marketplace" if url else ""}


@router.get("/marketplace")
async def list_marketplace(
    request: Request,
    current_user=Depends(deps.get_current_active_user),
):
    """代理官网市场列表"""
    return await _proxy_to_server("GET", "/plugins/marketplace", request, params=dict(request.query_params))


@router.get("/purchased")
async def list_purchased(
    request: Request,
    current_user=Depends(deps.get_current_active_user),
):
    """代理官网查询已购插件"""
    return await _proxy_to_server("GET", "/plugins/purchased", request, params=dict(request.query_params))


@router.post("/marketplace/purchase")
async def marketplace_purchase(
    request: Request,
    current_user=Depends(deps.get_current_active_user),
):
    """代理官网创建购买订单"""
    body = await request.json()
    return await _proxy_to_server("POST", "/plugins/marketplace/purchase", request, json_body=body)


@router.post("/marketplace/purchase/confirm")
async def marketplace_purchase_confirm(
    request: Request,
    current_user=Depends(deps.get_current_active_user),
):
    """代理官网确认购买订单"""
    body = await request.json()
    return await _proxy_to_server("POST", "/plugins/marketplace/purchase/confirm", request, json_body=body)


@router.post("/marketplace/install")
async def marketplace_install(
    request: Request,
    current_user=Depends(deps.get_current_active_user),
):
    """
    从官网市场下载并安装插件：
    1. 代理官网获取下载 URL + SHA256
    2. 下载插件 zip 到临时文件
    3. 调用 plugin_manager.install_plugin_from_zip 安装
    """
    body = await request.json()
    plugin_id = str(body.get("plugin_id") or "").strip()
    if not plugin_id:
        raise HTTPException(status_code=400, detail="plugin_id is required")

    # 权限校验
    user_role = str(getattr(current_user, "role", "") or "").lower()
    if user_role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Only admin/owner can install plugins")

    # 1. 代理官网获取下载信息（FIXED: 改用 oss-install 端点获取 download_url + sha256 + package_signature）
    download_info = await _proxy_to_server(
        "POST", "/plugins/marketplace/oss-install",
        request, json_body=body,
    )

    download_url = str(download_info.get("download_url") or "").strip()
    expected_sha256 = str(download_info.get("sha256") or download_info.get("package_sha256") or "").strip() or None
    expected_package_signature = str(download_info.get("package_signature") or download_info.get("signature") or "").strip() or None

    if not download_url:
        raise HTTPException(status_code=400, detail="No download URL returned from marketplace")

    # 2. 下载插件 zip
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix=f"plugin_{plugin_id}_")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            timeout = aiohttp.ClientTimeout(total=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = _instance_headers(b"")  # 下载可能也需要实例认证
                auth = _forward_auth_headers(request)
                headers.update(auth)
                async with session.get(download_url, headers=headers) as resp:
                    if resp.status != 200:
                        raise HTTPException(status_code=502, detail=f"Download failed: HTTP {resp.status}")
                    async for chunk in resp.content.iter_chunked(1024 * 256):
                        f.write(chunk)

        # 3. 本地安装（FIXED: 传入 package_signature 进行 ed25519 签名校验）
        result = plugin_manager.install_plugin_from_zip(
            tmp_path,
            tenant_id=str(getattr(current_user, "tenant_id", "default") or "default"),
            expected_sha256=expected_sha256,
            expected_package_signature=expected_package_signature,
        )
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)[:500])
    except Exception as e:
        logger.error(f"Marketplace install failed for {plugin_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Marketplace install failed: {str(e)[:200]}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError as e:
            # finally 中临时文件清理失败不应掩盖主流程异常，但需保留 debug 痕迹以便排查
            logger.debug(f"Temp file cleanup failed for {tmp_path}: {e}")
