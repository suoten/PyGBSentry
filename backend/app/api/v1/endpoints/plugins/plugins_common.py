"""
plugins_common — 共享工具函数、常量、Pydantic 模型、全局缓存变量。
所有子模块通过本文件中转共享，禁止子模块间直接交叉 import。
"""

import re
import asyncio
import json
import os
import shutil
import uuid
import hashlib
import time
import zipfile
import importlib
import sys
from app.core.http_client import get_http_client
import httpx
from datetime import datetime, timezone
from urllib.parse import urlparse
from pathlib import Path as FSPath
from typing import Literal

from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plugin_manager import (
    plugin_manager,
    HOOK_ON_STARTUP,
)
from app.db.session import get_db, engine
from app.core.config import settings
from app.core.archive import safe_extract_zip, UnsafeArchiveError
from app.db.base import Base
from app.models.user import User
from app.models.system_setting import SystemSetting
from app.services.license_service import (
    verify_license_payload,
    manifest_signature_install_error,
    verify_ed25519_signature,
)
from app.services.auth_audit import safe_auth_audit
from app.api import deps

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

from loguru import logger


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLUGIN_DIR = "plugins"
MARKETPLACE_CATALOG_PATH = os.path.join(PLUGIN_DIR, "marketplace.json")
BACKEND_ROOT_DIR = FSPath(__file__).resolve().parents[4]  # backend/
PLUGIN_DIR_ABS = BACKEND_ROOT_DIR / PLUGIN_DIR

# ---------------------------------------------------------------------------
# Global cache variables
# ---------------------------------------------------------------------------

# ---- stream_health runtime endpoint cache (avoid hammering ZLM) ----
_STREAM_HEALTH_CACHE_LOCK = asyncio.Lock()
_STREAM_HEALTH_CACHE_TS: float = 0.0
_STREAM_HEALTH_CACHE_RAW: list[dict] = []
_STREAM_HEALTH_CACHE_META: dict = {}

# OSS：GET /purchased 与付费插件 runtime 校验共用，减少对服务器版的 HTTP 频率
_PURCHASED_PROXY_CACHE_LOCK = asyncio.Lock()
_PURCHASED_PROXY_CACHE: dict[tuple[str, str, str], tuple[float, frozenset[str]]] = {}
# OSS：paid runtime 在线授权校验结果短缓存，减少高频 runtime 接口请求对服务器版压力
_RUNTIME_ENTITLEMENT_CACHE_LOCK = asyncio.Lock()
_RUNTIME_ENTITLEMENT_CACHE: dict[tuple[str, str, str, str], tuple[float, bool, int, str]] = {}

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class MarketplaceInstallRequest(BaseModel):
    plugin_id: str
    package_url: str | None = None

class PluginTableQueryRequest(BaseModel):
    limit: int = 50
    offset: int = 0
    order_by: str | None = None
    desc: bool = True
    where_eq: dict[str, str | int | float | bool | None] | None = None
    where_gte: dict[str, str | int | float] | None = None
    where_lte: dict[str, str | int | float] | None = None

class PluginTableExportRequest(PluginTableQueryRequest):
    columns: list[str] | None = None
    max_rows: int = 100000

class LicenseVerifyRequest(BaseModel):
    plugin_id: str
    feature_code: str
    tenant_id: str = "default"
    license_data: dict

class LicenseSignRequest(BaseModel):
    license_data: dict

class EmbeddedPurchaseRequest(BaseModel):
    plugin_id: str
    billing_period: Literal["monthly", "yearly", "perpetual"] = "monthly"

class MobilePluginEntry(BaseModel):
    plugin_id: str
    name: str
    platform: Literal["mobile", "miniprogram"]
    entry_type: Literal["h5", "webview", "plugin", "native", "none"] = "none"
    entry_url: str | None = None
    entry_url_template: str | None = None

class PluginRuntimeConfigUpdate(BaseModel):
    config: dict

class FaceDbDeleteRequest(BaseModel):
    person_id: str

class AlertTestRequest(BaseModel):
    """
    第三方告警通知测试请求：
    - channel: sms_alert / wecom_alert / feishu_alert / all
    - target: 可选，用于在 message 中标注本次测试（如测试人或备注）
    """
    channel: str = "all"
    target: str | None = None

class HookTimeoutTestRequest(BaseModel):
    """
    用于验证：当 `PLUGIN_HOOK_EXEC_TIMEOUT_SECONDS` 配置开启时，Hook 超时会触发 HOOK_ON_ALARM 告警链路。
    - hook_name: 触发超时的目标 Hook 名称（非 on_alarm 本身）
    - sleep_seconds: 让回调睡眠的时长（应 > 超时时间以触发超时）
    """
    hook_name: str
    sleep_seconds: float | None = None
    alarm_capture_timeout_seconds: float = 3.0
    log_to_file: bool = True

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _uuid7_hex(n: int = 16) -> str:
    return _uuid7_impl().hex[:n]

def _purchased_proxy_base_url() -> str:
    base_url = (settings.PLUGIN_MARKETPLACE_BASE_URL or "").rstrip("/")
    record_url = (settings.PLUGIN_SERVER_RECORD_URL or "").strip()
    if record_url:
        parsed = urlparse(record_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else base_url
    return base_url

def _authorization_for_server_proxy(request: Request) -> str | None:
    """转发到服务器版时优先使用 Authorization，否则使用 ?token=（与 deps / iframe 一致）。"""
    auth = (request.headers.get("Authorization") or "").strip()
    if auth:
        return auth
    tok = (request.query_params.get("token") or "").strip()
    if not tok:
        return None
    if tok.lower().startswith("bearer "):
        return tok
    return f"Bearer {tok}"

def _purchased_proxy_cache_key(request: Request, current_user: User) -> tuple[str, str, str]:
    uid = str(getattr(current_user, "id", "") or "")
    tid = str(getattr(current_user, "tenant_id", None) or "default").strip() or "default"
    auth = (request.headers.get("Authorization") or "").strip()
    tok = (request.query_params.get("token") or "").strip()
    ak = (request.headers.get("x-api-key") or request.headers.get("X-API-Key") or "").strip()
    fp = hashlib.sha256(f"{auth}\0{tok}\0{ak}".encode("utf-8")).hexdigest()[:32]
    return (uid, tid, fp)

async def _fetch_purchased_plugin_ids_uncached(request: Request, current_user: User) -> frozenset[str]:
    base_url = _purchased_proxy_base_url()
    if not base_url:
        return frozenset()
    url = f"{base_url}/api/v1/plugins/purchased"
    try:
        headers = {"Content-Type": "application/json"}
        auth = _authorization_for_server_proxy(request)
        if auth:
            headers["Authorization"] = auth
        resp = await (await get_http_client()).get(url, headers=headers, timeout=8)  # 同步requests→异步httpx，避免阻塞事件循环
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "plugin_ids" in data:
                return frozenset(
                    str(pid) for pid in (data.get("plugin_ids") or []) if pid is not None
                )
    except Exception as e:
        logger.debug(f"Non-critical operation failed: {e}")
    return frozenset()

async def get_purchased_plugin_ids_cached(request: Request, current_user: User) -> frozenset[str]:
    ttl = settings.PLUGIN_PURCHASED_PROXY_CACHE_SECONDS
    if ttl <= 0:
        return await _fetch_purchased_plugin_ids_uncached(request, current_user)
    key = _purchased_proxy_cache_key(request, current_user)
    now = time.monotonic()
    async with _PURCHASED_PROXY_CACHE_LOCK:
        hit = _PURCHASED_PROXY_CACHE.get(key)
        if hit is not None and hit[0] > now:
            return hit[1]
    fresh = await _fetch_purchased_plugin_ids_uncached(request, current_user)
    async with _PURCHASED_PROXY_CACHE_LOCK:
        if len(_PURCHASED_PROXY_CACHE) > 256:
            _PURCHASED_PROXY_CACHE.clear()
        _PURCHASED_PROXY_CACHE[key] = (now + float(ttl), fresh)
    return fresh

async def invalidate_purchased_plugin_ids_cache_for_user(user_id: str) -> None:
    """安装/卸载等变更后清除该用户在已购代理缓存中的全部指纹条目，避免长时间命中过期的已购列表。"""
    uid = str(user_id or "").strip()
    if not uid:
        return
    async with _PURCHASED_PROXY_CACHE_LOCK:
        for k in list(_PURCHASED_PROXY_CACHE.keys()):
            if k[0] == uid:
                _PURCHASED_PROXY_CACHE.pop(k, None)

# Alias for convenience (used by plugins_install, plugins_market)
_invalidate_purchased_plugin_ids_cache_for_user = invalidate_purchased_plugin_ids_cache_for_user

def _resolve_paid_runtime_auth_mode() -> str:
    """
    解析 paid runtime 授权策略（兼容旧开关）。
    """
    raw = str(settings.PLUGIN_PAID_RUNTIME_AUTH_MODE or "compat").strip().lower()
    valid = {"compat", "cache_only", "online_strict", "online_fail_open", "online_prefer_cache"}
    if raw in valid and raw != "compat":
        return raw

    # compat：沿用历史字段语义
    runtime_online = settings.PLUGIN_PAID_RUNTIME_INSTALL_CHECK
    strict = settings.PLUGIN_PAID_INSTALL_CHECK_STRICT
    if runtime_online and strict:
        return "online_strict"
    if runtime_online and not strict:
        return "online_fail_open"
    return "cache_only"

def _runtime_entitlement_cache_key(request: Request, current_user: User, plugin_id: str) -> tuple[str, str, str, str]:
    uid, tid, fp = _purchased_proxy_cache_key(request, current_user)
    return (uid, tid, str(plugin_id or "").strip(), fp)

def _runtime_online_check_cache_ttl() -> int:
    return max(0, settings.PLUGIN_PAID_RUNTIME_ONLINE_CHECK_CACHE_SECONDS)

def _server_base_url_for_install_check() -> str:
    """
    从 PLUGIN_SERVER_RECORD_URL 或 PLUGIN_MARKETPLACE_BASE_URL 推导服务器版 base URL。
    """
    record_url = (settings.PLUGIN_SERVER_RECORD_URL or "").strip()
    if record_url:
        try:
            parsed = urlparse(record_url)
            if parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
        except Exception as e:
            logger.debug(f"Non-critical operation failed: {e}")
    return (settings.PLUGIN_MARKETPLACE_BASE_URL or "").rstrip("/")

async def _check_paid_plugin_entitlement_online_once(
    plugin_id: str,
    authorization: str | None,
    *,
    strict_response_body: bool,
) -> tuple[bool, int, str]:
    """
    在线调用服务器版 install-check。
    返回：(ok, status_code, detail)
    """
    base = _server_base_url_for_install_check()
    if not base:
        return (False, 503, "Server edition address not configured, cannot verify authorization online")  # i18n

    url = f"{base}/api/v1/plugins/install-check"
    try:
        headers = {"Content-Type": "application/json"}
        if authorization:
            headers["Authorization"] = authorization
        try:
            from app.core.plugin_manager import plugin_manager
            instance_headers = plugin_manager.get_oss_instance_headers(
                json.dumps({"plugin_id": plugin_id}).encode("utf-8")
            )
            if instance_headers:
                headers.update(instance_headers)
        except Exception as e:
            logger.debug(f"Failed to build plugin request headers: {e}")  # i18n
        resp = await (await get_http_client()).post(
            url,
            headers=headers,
            json={"plugin_id": plugin_id},
            timeout=8,
        )  # 同步requests→异步httpx，避免阻塞事件循环
        if resp.status_code == 402:
            return (False, 402, "SUBSCRIPTION_EXPIRED")
        if resp.status_code == 401:
            return (False, 401, "Server-side login verification failed, please login again")  # i18n
        if resp.status_code == 403:
            detail403 = "PLUGIN_NOT_PURCHASED"
            try:
                body = resp.json()
                if isinstance(body, dict) and body.get("detail") is not None:
                    raw = body["detail"]
                    if isinstance(raw, str):
                        detail403 = raw
                    elif isinstance(raw, dict):
                        detail403 = str(raw.get("reason_code") or raw.get("reasonCode") or detail403)
            except Exception as e:
                logger.debug(f"Non-critical operation failed: {e}")
            return (False, 403, detail403)
        if 200 <= resp.status_code < 300:
            if strict_response_body:
                try:
                    body = resp.json()
                except Exception as e:
                    logger.debug(f"Operation failed, returning default value: {e}")  # i18n
                    body = {}
                if not (isinstance(body, dict) and body.get("ok")):
                    return (False, 502, "Server edition install-check returned abnormal, please retry later or contact admin")  # i18n
            return (True, 200, "OK")

        msg = ""
        try:
            err = resp.json()
            if isinstance(err, dict) and err.get("detail"):
                msg = str(err["detail"])
        except Exception as e:
            logger.debug(f"Operation failed, returning default value: {e}")  # i18n
            msg = (resp.text or "")[:200]
        return (False, 502, msg or f"install-check failed (HTTP {resp.status_code})")  # i18n
    except httpx.TimeoutException:
        return (False, 504, "install-check request timeout, check network to server edition and retry")  # 同步requests→异步httpx，避免阻塞事件循环
    except httpx.HTTPError as e:
        return (False, 502, f"Cannot connect to server edition for install-check: {e}")  # 同步requests→异步httpx，避免阻塞事件循环
    except Exception as e:
        return (False, 502, f"install-check exception: {e}")  # i18n

def _entitlement_error_detail(code: str, *, message: str | None = None) -> dict:
    """
    统一付费插件授权失败的错误体（供前端稳定映射）。
    """
    normalized = str(code or "").strip() or "UNKNOWN"
    msg = (message or "").strip()
    if normalized == "SUBSCRIPTION_EXPIRED":
        return {
            "reason_code": "SUBSCRIPTION_EXPIRED",
            "message": msg or "Current tenant subscription has expired, cannot install/use paid plugins",  # i18n
            "suggestion": "Please renew/restore subscription in server edition user portal first, then retry in OSS edition",  # i18n
            "retryable": False,
        }
    if normalized == "PLUGIN_NOT_PURCHASED":
        return {
            "reason_code": "PLUGIN_NOT_PURCHASED",
            "message": msg or "Paid plugin not purchased or tenant not authorized",  # i18n
            "suggestion": "Please complete purchase/renewal in server edition user portal first, then install in OSS edition",  # i18n
            "retryable": False,
        }
    return {
        "reason_code": normalized,
        "message": msg or "Paid plugin authorization verification failed",  # i18n
        "suggestion": "Please retry later, or contact admin to check server edition authorization status",  # i18n
        "retryable": False,
    }

async def _check_paid_plugin_entitlement_online_cached(
    request: Request,
    current_user: User,
    plugin_id: str,
    authorization: str | None,
    *,
    strict_response_body: bool,
) -> tuple[bool, int, str]:
    ttl = _runtime_online_check_cache_ttl()
    key = _runtime_entitlement_cache_key(request, current_user, plugin_id)
    now = time.monotonic()
    if ttl > 0:
        async with _RUNTIME_ENTITLEMENT_CACHE_LOCK:
            hit = _RUNTIME_ENTITLEMENT_CACHE.get(key)
            if hit is not None and hit[0] > now:
                return (hit[1], hit[2], hit[3])

    result = await _check_paid_plugin_entitlement_online_once(
        plugin_id,
        authorization,
        strict_response_body=strict_response_body,
    )  # 同步requests→异步httpx，避免阻塞事件循环
    if ttl > 0:
        async with _RUNTIME_ENTITLEMENT_CACHE_LOCK:
            if len(_RUNTIME_ENTITLEMENT_CACHE) > 1024:
                _RUNTIME_ENTITLEMENT_CACHE.clear()
            _RUNTIME_ENTITLEMENT_CACHE[key] = (now + float(ttl), result[0], result[1], result[2])
    return result

def _validate_plugin_asset_id(plugin_id: str) -> str:
    pid = str(plugin_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", pid):
        raise HTTPException(status_code=400, detail="Invalid plugin_id")
    return pid

def _plugin_dir_abs(plugin_id: str) -> FSPath:
    pid = _validate_plugin_asset_id(plugin_id)
    return (PLUGIN_DIR_ABS / pid).resolve()

def _ensure_loaded_plugin(plugin_id: str) -> dict:
    pid = str(plugin_id or "").strip()
    meta = plugin_manager.metadata.get(pid)
    if not pid or not isinstance(meta, dict):
        raise HTTPException(status_code=404, detail="Plugin not found or not loaded")
    return meta

def _safe_join_asset(root: FSPath, plugin_id: str, asset_path: str) -> FSPath:
    # 禁止路径穿越
    ap = (asset_path or "").lstrip("/").replace("\\", "/")
    if not ap:
        ap = "index.html"
    if ".." in ap.split("/"):
        raise HTTPException(status_code=400, detail="Invalid resource path")
    candidate = (root / plugin_id / ap).resolve()
    if not str(candidate).startswith(str((root / plugin_id).resolve())):
        raise HTTPException(status_code=400, detail="Invalid resource path")
    return candidate

def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"

def _parse_face_db_identities(raw: dict) -> list[dict]:
    """
    期望格式：
      {"identities":[{"person_id":"u1","name":"张三","embedding":[...]}]}
    """
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="face_db must be a JSON object")
    ids = raw.get("identities")
    if not isinstance(ids, list):
        raise HTTPException(status_code=400, detail="face_db.identities must be an array")
    out: list[dict] = []
    for it in ids:
        if not isinstance(it, dict):
            continue
        emb = it.get("embedding")
        if not isinstance(emb, list) or len(emb) < 8:
            continue
        try:
            emb2 = [float(x) for x in emb]
        except Exception as e:
            logger.debug(f"Skipped: {e}")  # i18n
            continue
        out.append(
            {
                "person_id": str(it.get("person_id") or "").strip() or None,
                "name": str(it.get("name") or "").strip() or None,
                "embedding_dim": len(emb2),
            }
        )
    return out

def _load_face_db_raw(path: FSPath) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return {"identities": []}
        if not isinstance(raw.get("identities"), list):
            raw["identities"] = []
        return raw
    except Exception as e:
        logger.debug(f"Operation failed, returning default value: {e}")  # i18n
        return {"identities": []}

def _face_db_path_abs() -> FSPath:
    base = _plugin_dir_abs("face_recognition_suite")
    return (base / "face_db" / "identities.json").resolve()

def _guess_import_name_from_pip(pip_pkg: str) -> str:
    s = str(pip_pkg or "").strip()
    if not s:
        return s
    s = s.split(";", 1)[0].strip()
    s = s.split("[", 1)[0].strip()
    for sep in ("==", ">=", "<=", "~=", "!="):
        if sep in s:
            s = s.split(sep, 1)[0].strip()
    if not s:
        return s
    m = {
        "opencv-python": "cv2",
        "opencv_contrib_python": "cv2",
        "onnxruntime": "onnxruntime",
        "ultralytics": "ultralytics",
        "insightface": "insightface",
        "paddleocr": "paddleocr",
        "easyocr": "easyocr",
        "torch": "torch",
    }
    sl = s.lower().replace("-", "_")
    return m.get(s.lower(), sl)

def _is_import_available(import_name: str) -> bool:
    try:
        spec = importlib.util.find_spec(import_name)
        return spec is not None
    except Exception as e:
        logger.debug(f"Operation failed, returning default value: {e}")  # i18n
        return False

async def _pip_install_into_vendor(vendor_dir: str, pip_pkg: str, *, timeout_seconds: int) -> None:
    os.makedirs(vendor_dir, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        str(pip_pkg),
        "--no-cache-dir",
        "--target",
        vendor_dir,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )  # 同步requests→异步httpx，避免阻塞事件循环
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise HTTPException(status_code=500, detail=f"Dependency install timeout ({timeout_seconds}s)")
        if proc.returncode != 0:
            stderr_output = stderr.decode("utf-8", errors="replace") if stderr else ""
            raise HTTPException(status_code=500, detail=f"Dependency install failed: {stderr_output[:500]}")
    except HTTPException:
        raise
    except (FileNotFoundError, OSError) as e:
        raise HTTPException(status_code=500, detail=f"pip command execution failed: {str(e)}")

def _collect_menu_entries(meta: dict, plugin_id: str) -> list[dict]:
    menu = meta.get("menu")
    if isinstance(menu, dict):
        menu_items = [menu]
    elif isinstance(menu, list):
        menu_items = [x for x in menu if isinstance(x, dict)]
    else:
        menu_items = []
    if not menu_items:
        menu_items = [{"title": meta.get("name") or meta.get("title") or plugin_id, "path": f"/plugins/runtime/{plugin_id}"}]
    out: list[dict] = []
    for it in menu_items:
        if not isinstance(it, dict):
            continue
        path = it.get("path") or f"/plugins/runtime/{plugin_id}"
        out.append({**it, "path": path})
    return out

def _validate_plugin_menu_conflicts(metadata: dict, plugin_id: str) -> None:
    """
    安装/上传时校验菜单路由冲突。
    """
    required_prefix = settings.PLUGIN_MENU_PATH_REQUIRED_PREFIX
    new_entries = _collect_menu_entries(metadata or {}, plugin_id)
    new_paths: set[str] = set()
    new_invalid: list[str] = []
    for e in new_entries:
        path = str(e.get("path") or "").strip()
        if not path:
            continue
        if not path.startswith(required_prefix):
            new_invalid.append(path)
        new_paths.add(path)
    if new_invalid:
        raise HTTPException(status_code=400, detail=f"menu.path must start with {required_prefix}：{new_invalid[:3]}")

    for other_pid, other_meta in plugin_manager.metadata.items():
        if str(other_pid).strip() == str(plugin_id).strip():
            continue
        other_entries = _collect_menu_entries(other_meta or {}, str(other_pid).strip())
        other_paths = {str(e.get("path") or "").strip() for e in other_entries if str(e.get("path") or "").strip()}
        conflict = new_paths.intersection(other_paths)
        if conflict:
            raise HTTPException(status_code=400, detail=f"menu.path conflicts with installed plugin：{sorted(list(conflict))[:3]}")

    new_frontend_urls: set[str] = set()
    for e in new_entries:
        fu = str(e.get("frontend_url") or "").strip()
        if not fu:
            continue
        if ".." in fu:
            raise HTTPException(status_code=400, detail="menu.frontend_url invalid (path traversal forbidden)")
        if fu.startswith("/api/"):
            continue
        if not fu.startswith("/"):
            raise HTTPException(status_code=400, detail=f"menu.frontend_url must start with /：{fu}")
        new_frontend_urls.add(fu)

    if new_frontend_urls:
        for other_pid, other_meta in plugin_manager.metadata.items():
            if str(other_pid).strip() == str(plugin_id).strip():
                continue
            other_entries = _collect_menu_entries(other_meta or {}, str(other_pid).strip())
            other_frontend_urls = {
                str(e.get("frontend_url") or "").strip()
                for e in other_entries
                if str(e.get("frontend_url") or "").strip() and not str(e.get("frontend_url") or "").strip().startswith("/api/")
            }
            conflict_fu = new_frontend_urls.intersection(other_frontend_urls)
            if conflict_fu:
                raise HTTPException(
                    status_code=400,
                    detail=f"menu.frontend_url conflicts with installed plugin: {sorted(list(conflict_fu))[:3]}",  # i18n
                )

def _normalize_dependency_items(metadata: dict, file_list: list[str]) -> list[dict]:
    deps: list[dict] = []
    raw = metadata.get("dependencies") or metadata.get("python_dependencies") or []
    if isinstance(raw, list):
        for it in raw:
            if isinstance(it, str):
                deps.append({"pip": it, "import": _guess_import_name_from_pip(it)})
            elif isinstance(it, dict):
                pip_pkg = it.get("pip") or it.get("package") or ""
                if not pip_pkg:
                    continue
                deps.append({"pip": str(pip_pkg), "import": str(it.get("import") or _guess_import_name_from_pip(str(pip_pkg)))})
    elif isinstance(raw, dict):
        pip_list = raw.get("pip") or raw.get("packages") or []
        if isinstance(pip_list, list):
            for p in pip_list:
                if isinstance(p, str):
                    deps.append({"pip": p, "import": _guess_import_name_from_pip(p)})

    if file_list and any(str(x).endswith("requirements.txt") for x in file_list):
        deps.append({"pip_from_file": True})
    return deps

async def _ensure_plugin_dependencies_installed(plugin_id: str, target_dir: str, metadata: dict, file_list: list[str]) -> None:
    if not settings.PLUGIN_AUTO_INSTALL_DEPENDENCIES:
        return
    vendor_dir = os.path.join(target_dir, settings.PLUGIN_DEPENDENCY_VENDOR_DIR_NAME)
    timeout_seconds = settings.PLUGIN_DEPENDENCY_INSTALL_TIMEOUT_SECONDS

    dep_items = _normalize_dependency_items(metadata or {}, file_list or [])
    req_path = os.path.join(target_dir, "requirements.txt")
    requirements: list[str] = []
    if os.path.exists(req_path):
        try:
            with open(req_path, "r", encoding="utf-8") as f:
                for line in f.readlines():
                    s = str(line).strip()
                    if not s or s.startswith("#"):
                        continue
                    requirements.append(s)
        except Exception as e:
            logger.debug(f"Operation failed, returning default value: {e}")  # i18n
            requirements = []

    vendor_dir = os.path.abspath(vendor_dir)
    if not dep_items or dep_items == [{"pip_from_file": True}]:
        dep_items = [{"pip": r, "import": _guess_import_name_from_pip(r)} for r in requirements] if requirements else []
    else:
        if requirements:
            dep_items = [d for d in dep_items if not d.get("pip_from_file")] + [{"pip": r, "import": _guess_import_name_from_pip(r)} for r in requirements]

    to_install: list[dict] = []
    for d in dep_items:
        pip_pkg = str(d.get("pip") or "").strip()
        if not pip_pkg:
            continue
        imp_name = str(d.get("import") or "").strip()
        if not imp_name:
            to_install.append({"pip": pip_pkg})
            continue
        if not _is_import_available(imp_name):
            to_install.append({"pip": pip_pkg})

    for it in to_install:
        await _pip_install_into_vendor(vendor_dir, it["pip"], timeout_seconds=timeout_seconds)  # 同步requests→异步httpx，避免阻塞事件循环

def _plugin_upgrade_backup_root() -> FSPath:
    raw = str(settings.PLUGIN_UPGRADE_BACKUP_DIR or "").strip()
    if raw:
        p = FSPath(raw)
        if not p.is_absolute():
            p = BACKEND_ROOT_DIR / p
        return p.resolve()
    return (PLUGIN_DIR_ABS / ".upgrade_backups").resolve()

def _create_plugin_upgrade_snapshot(plugin_id: str) -> dict:
    """
    升级快照：
    - 有旧版本时复制 plugins/{plugin_id} 到备份目录
    - 新装（无旧版本）仅返回标记，失败时走删除回滚
    """
    pid = _validate_plugin_asset_id(plugin_id)
    target_dir = (_plugin_dir_abs(pid)).resolve()
    has_existing = target_dir.exists() and target_dir.is_dir()
    enabled = settings.PLUGIN_UPGRADE_BACKUP_ENABLED
    snap = {
        "plugin_id": pid,
        "enabled": enabled,
        "has_existing": bool(has_existing),
        "backup_dir": "",
    }
    if not enabled or not has_existing:
        return snap

    backup_root = _plugin_upgrade_backup_root()
    backup_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    backup_dir = (backup_root / f"{pid}_{ts}_{_uuid7_hex(8)}").resolve()
    shutil.copytree(str(target_dir), str(backup_dir))
    snap["backup_dir"] = str(backup_dir)
    return snap

def _cleanup_plugin_upgrade_snapshot(snapshot: dict) -> None:
    if not isinstance(snapshot, dict):
        return
    backup_dir = str(snapshot.get("backup_dir") or "").strip()
    if not backup_dir:
        return
    try:
        p = FSPath(backup_dir)
        if p.exists() and p.is_dir():
            shutil.rmtree(str(p), ignore_errors=True)
    except Exception as e:
        logger.debug(f"Non-critical operation failed: {e}")

def _restore_plugin_upgrade_snapshot(snapshot: dict) -> bool:
    """
    回滚插件文件快照。返回是否执行了恢复动作。
    """
    if not isinstance(snapshot, dict):
        return False
    pid = str(snapshot.get("plugin_id") or "").strip()
    if not pid:
        return False

    target_dir = (_plugin_dir_abs(pid)).resolve()
    has_existing = bool(snapshot.get("has_existing"))
    backup_dir = str(snapshot.get("backup_dir") or "").strip()

    try:
        if target_dir.exists() and target_dir.is_dir():
            shutil.rmtree(str(target_dir), ignore_errors=True)
    except Exception as e:
        logger.debug(f"Non-critical operation failed: {e}")

    if has_existing and backup_dir:
        try:
            src = FSPath(backup_dir)
            if src.exists() and src.is_dir():
                shutil.copytree(str(src), str(target_dir))
                return True
        except Exception as e:
            logger.debug(f"Operation failed, returning default value: {e}")  # i18n
            return False
    return True

async def _recover_plugins_after_failed_upgrade(snapshot: dict | None = None) -> None:
    """
    安装/升级失败后的统一恢复：
    1) 尝试恢复快照（若有）
    2) 重新 load 插件
    3) 重新触发 startup hook
    """
    if isinstance(snapshot, dict):
        _restore_plugin_upgrade_snapshot(snapshot)
    try:
        plugin_manager.load_plugins()
        await plugin_manager.emit(HOOK_ON_STARTUP)
    except Exception as e:
        logger.debug(f"Non-critical operation failed: {e}")

def _peek_plugin_json_from_zip(zip_path: str) -> dict:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if "plugin.json" not in zf.namelist():
                return {}
            with zf.open("plugin.json") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug(f"Operation failed, returning default value: {e}")  # i18n
        return {}

def _parse_version_tuple(v: str | None) -> tuple[int, int, int]:
    if not v:
        return (0, 0, 0)
    parts = str(v).strip().split(".")
    nums: list[int] = []
    for p in parts[:3]:
        try:
            nums.append(max(0, int(p)))
        except Exception as e:
            logger.debug(f"Non-critical operation failed: {e}")
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)  # type: ignore[return-value]

def _is_version_lt(a: str | None, b: str | None) -> bool:
    return _parse_version_tuple(a) < _parse_version_tuple(b)

def _version_lt(current: str, latest: str) -> bool:
    """当前版本是否小于服务端版本。"""
    a, b = _parse_version_tuple(current), _parse_version_tuple(latest)
    for i in range(max(len(a), len(b))):
        x, y = (a[i] if i < len(a) else 0), (b[i] if i < len(b) else 0)
        if x < y:
            return True
        if x > y:
            return False
    return False

def _plan_install_or_upgrade_from_zip(
    zip_path: str,
    *,
    expected_plugin_id: str | None = None,
) -> dict:
    """
    升级前检查：
    - ZIP 内 plugin_id 与请求目标一致
    - 禁止无意降级（可配置放开）
    """
    meta = _peek_plugin_json_from_zip(zip_path) or {}
    pid = str(meta.get("id") or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="Invalid plugin package: plugin.json missing id")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", pid):
        raise HTTPException(status_code=400, detail="Invalid plugin id (alphanumeric, -, _, max 64 chars)")  # i18n

    exp = str(expected_plugin_id or "").strip()
    if exp and exp != pid:
        raise HTTPException(status_code=400, detail=f"Plugin package id({pid}) does not match target plugin({exp}), installation aborted")  # i18n

    cur_version = str((plugin_manager.metadata.get(pid, {}) or {}).get("version") or "").strip()
    new_version = str(meta.get("version") or "").strip()
    allow_downgrade = settings.PLUGIN_UPGRADE_ALLOW_DOWNGRADE
    if cur_version and new_version and _is_version_lt(new_version, cur_version) and not allow_downgrade:
        raise HTTPException(
            status_code=400,
            detail=f"Downgrade detected (current {cur_version} -> new {new_version}), blocked by default. Set PLUGIN_UPGRADE_ALLOW_DOWNGRADE=true to allow.",  # i18n
        )

    operation = "upgrade" if cur_version else "install"
    return {
        "plugin_id": pid,
        "operation": operation,
        "current_version": cur_version or None,
        "incoming_version": new_version or None,
    }

async def _precheck_paid_plugin_install(plugin_payload: dict, authorization: str | None) -> None:
    if not plugin_payload:
        return
    if str(plugin_payload.get("type") or "").lower() != "paid":
        return
    strict = settings.PLUGIN_PAID_INSTALL_CHECK_STRICT
    ok, status_code, detail = await _check_paid_plugin_entitlement_online_once(  # 同步requests→异步httpx，避免阻塞事件循环
        str(plugin_payload.get("id") or ""),
        authorization,
        strict_response_body=strict,
    )
    if ok:
        return
    if strict or status_code in (401, 402, 403):
        normalized = str(detail or "").strip()
        if status_code == 402 and normalized == "SUBSCRIPTION_EXPIRED":
            raise HTTPException(status_code=402, detail=_entitlement_error_detail("SUBSCRIPTION_EXPIRED"))
        if status_code == 403 and normalized == "PLUGIN_NOT_PURCHASED":
            raise HTTPException(status_code=403, detail=_entitlement_error_detail("PLUGIN_NOT_PURCHASED"))
        raise HTTPException(status_code=status_code, detail=detail)

def _normalize_marketplace_base() -> str:
    return (settings.PLUGIN_MARKETPLACE_BASE_URL or settings.PLUGIN_MARKETPLACE_BASE_URL).rstrip("/")

def _allowed_market_host() -> str:
    parsed = urlparse(_normalize_marketplace_base())
    return (parsed.hostname or "").lower()

def _is_allowed_package_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    allowed = _allowed_market_host()
    if host in {"localhost", "127.0.0.1"}:
        return True
    return host == allowed or host.endswith(f".{allowed}")

def _read_marketplace_catalog() -> list[dict]:
    if not os.path.exists(MARKETPLACE_CATALOG_PATH):
        return []
    with open(MARKETPLACE_CATALOG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    items = [item for item in data if isinstance(item, dict)]
    for it in items:
        if isinstance(it, dict) and "trial_days" in it:
            it.pop("trial_days", None)
    return items

async def _fetch_marketplace_items() -> list[dict]:
    base_url = _normalize_marketplace_base()
    if not base_url:
        return _read_marketplace_catalog()
    url = f"{base_url}/api/v1/plugins/marketplace"
    try:
        response = await (await get_http_client()).get(url, timeout=10)  # 同步requests→异步httpx，避免阻塞事件循环
    except Exception as e:
        logger.warning("Failed to fetch remote marketplace: %s, falling back to local catalog", e)
        return _read_marketplace_catalog()
    if response.status_code >= 400:
        logger.warning("Marketplace server returned %s, falling back to local catalog", response.status_code)
        return _read_marketplace_catalog()
    try:
        items = response.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Plugin marketplace returned invalid data")
    if not isinstance(items, list):
        raise HTTPException(status_code=502, detail="Plugin marketplace data format invalid")
    cleaned = [item for item in items if isinstance(item, dict)]
    for it in cleaned:
        if isinstance(it, dict) and "trial_days" in it:
            it.pop("trial_days", None)
    for it in cleaned:
        if not isinstance(it, dict):
            continue
        pid = str(it.get("id") or it.get("plugin_id") or "").strip()
        title = it.get("title")
        name = it.get("name")
        if not name:
            if isinstance(title, str) and title.strip():
                it["name"] = title.strip()
            elif pid:
                it["name"] = pid

        menu = it.get("menu")
        if isinstance(menu, dict):
            mtitle = menu.get("title")
            if (not mtitle) and isinstance(it.get("name"), str):
                menu["title"] = str(it.get("name"))
    return cleaned

async def _resolve_marketplace_install_payload(plugin_id: str) -> dict:
    items = await _fetch_marketplace_items()  # 同步requests→异步httpx，避免阻塞事件循环
    for item in items:
        if str(item.get("id")) == plugin_id:
            return item
    raise HTTPException(status_code=404, detail="Plugin not found in marketplace listing")

def _normalize_hex_sha256(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip().lower()
    if len(s) != 64:
        return None
    try:
        int(s, 16)
    except ValueError:
        return None
    return s

def _expected_sha256_from_catalog_item(item: dict) -> str | None:
    for key in ("package_sha256", "sha256", "packageSha256"):
        hx = _normalize_hex_sha256(item.get(key))
        if hx:
            return hx
    return None

def _expected_package_signature_from_catalog_item(item: dict) -> str | None:
    if not isinstance(item, dict):
        return None
    for key in ("package_signature", "packageSignature", "signature", "packageSig"):
        sig = item.get(key)
        if isinstance(sig, str) and sig.strip():
            return sig.strip()
    return None

def _sha256_hex_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()

def _verify_file_sha256(path: str, expected_hex: str) -> None:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    actual = h.hexdigest().lower()
    exp = (expected_hex or "").strip().lower()
    if actual != exp:
        raise HTTPException(status_code=400, detail="Plugin package SHA256 mismatch, install aborted")

def _ensure_oss_compatible(plugin_payload: dict) -> None:
    status = str(plugin_payload.get("status") or "active").lower()
    if status == "deprecated":
        raise HTTPException(status_code=400, detail="This plugin has been deprecated, new installations are not allowed")  # i18n
    min_oss = str(plugin_payload.get("min_oss_version") or "").strip() or None
    if min_oss:
        current = settings.PROJECT_VERSION
        if _is_version_lt(current, min_oss):
            raise HTTPException(status_code=400, detail=f"Current open-source version {current} is too low, plugin requires >= {min_oss}. Please upgrade first.")  # i18n
    max_oss = str(plugin_payload.get("max_oss_version") or "").strip() or None
    if max_oss:
        current = settings.PROJECT_VERSION
        if not _is_version_lt(current, max_oss):
            raise HTTPException(status_code=400, detail=f"Current open-source version {current} is too high, plugin only supports <= {max_oss}. Contact the plugin developer.")  # i18n

async def _notify_server_plugin_event(
    plugin_id: str,
    action: str,
    user_id: str,
    tenant_id: str,
    authorization: str | None,
    plugin_version: str | None = None,
) -> None:
    """安装/卸载成功后通知服务器版，用于验证登录并记录购买、安装记录。"""
    url = settings.PLUGIN_SERVER_RECORD_URL or ""
    if not url or not url.strip():
        return
    try:
        headers = {"Content-Type": "application/json"}
        if authorization:
            headers["Authorization"] = authorization
        body = {
            "plugin_id": plugin_id,
            "action": action,
            "user_id": user_id,
            "tenant_id": tenant_id or "default",
        }
        if plugin_version:
            body["plugin_version"] = plugin_version
        resp = await (await get_http_client()).post(url.strip(), json=body, headers=headers, timeout=10)  # 同步requests→异步httpx，避免阻塞事件循环
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="Server-side login verification failed, please log in again")  # i18n
        if resp.status_code == 402:
            raise HTTPException(status_code=402, detail=_entitlement_error_detail("SUBSCRIPTION_EXPIRED"))
        if resp.status_code == 403:
            detail403 = "PLUGIN_NOT_PURCHASED"
            try:
                body = resp.json()
                if isinstance(body, dict) and body.get("detail") is not None:
                    raw = body["detail"]
                    if isinstance(raw, str):
                        detail403 = raw
                    elif isinstance(raw, dict):
                        detail403 = str(raw.get("reason_code") or raw.get("reasonCode") or detail403)
            except Exception as e:
                logger.debug(f"Non-critical operation failed: {e}")
            if str(detail403).strip() == "PLUGIN_NOT_PURCHASED":
                raise HTTPException(status_code=403, detail=_entitlement_error_detail("PLUGIN_NOT_PURCHASED"))
            raise HTTPException(status_code=403, detail=detail403)
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Server record failed: {resp.status_code}",  # i18n
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.debug(f"Non-critical operation failed: {e}")

def _rollback_installed_plugin_files(plugin_id: str) -> None:
    """当服务器端硬拦截导致安装失败时，回滚已落盘的插件文件。"""
    pid = (plugin_id or "").strip()
    if not pid:
        return
    target_dir = os.path.join(PLUGIN_DIR, pid)
    target_file = os.path.join(PLUGIN_DIR, f"{pid}.py")
    try:
        if os.path.isdir(target_dir):
            shutil.rmtree(target_dir)
    except Exception as e:
        logger.debug(f"Non-critical operation failed: {e}")
    try:
        if os.path.exists(target_file):
            os.remove(target_file)
    except Exception as e:
        logger.debug(f"Non-critical operation failed: {e}")
    try:
        plugin_manager.load_plugins()
    except Exception as e:
        logger.debug(f"Non-critical operation failed: {e}")

def _sanitize_plugin_tables(
    tables: list | None,
    *,
    plugin_id: str | None = None,
    enforce_plugin_id_prefix: bool = False,
) -> list[str]:
    """
    插件 tables 仅允许字母数字下划线，避免注入。
    """
    if not isinstance(tables, list):
        return []
    safe = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    out: list[str] = []
    for t in tables:
        if isinstance(t, str) and safe.match(t):
            out.append(t)
    if enforce_plugin_id_prefix and plugin_id:
        pid = str(plugin_id).strip().replace("-", "_").lower()
        if pid:
            need = f"plugin_{pid}_"
            bad = [x for x in out if not x.lower().startswith(need)]
            if bad:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Plugin declared table names must have prefix {need} (PLUGIN_TABLES_REQUIRE_PLUGIN_ID_PREFIX enabled):"  # i18n
                        + ", ".join(bad[:8])
                    ),
                )
    return out

async def _ensure_plugin_tables_created(*, tables: list[str] | None) -> None:
    """
    安装成功后建表。
    S-07 — 使用tables参数仅创建指定表，而非Base.metadata.create_all创建全部表
    """
    if not tables:
        return
    try:
        table_objects = [Base.metadata.tables[t] for t in tables if t in Base.metadata.tables]
        if table_objects:
            async with engine.begin() as conn:
                await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=table_objects))
    except Exception as e:
        logger.debug(f"Operation failed, returning default value: {e}")
        return

def _build_menu_entries(purchased_plugin_ids: set[str] | None = None) -> list[dict]:
    entries: list[dict] = []
    for plugin_id, meta in plugin_manager.metadata.items():
        plugin_type = str((meta or {}).get("type") or "").lower()
        if purchased_plugin_ids is not None and plugin_type == "paid" and plugin_id not in purchased_plugin_ids:
            continue
        menu = meta.get("menu")
        if isinstance(menu, dict):
            menu = [menu]
        if not isinstance(menu, list):
            continue
        for raw in menu:
            if not isinstance(raw, dict):
                continue
            title = raw.get("title") or meta.get("name") or meta.get("title") or plugin_id
            path = raw.get("path") or f"/plugins/runtime/{plugin_id}"
            frontend_url = (
                raw.get("frontend_url")
                or meta.get("frontend_url")
                or f"/api/v1/plugins/plugin-assets/{plugin_id}/index.html"
            )
            entries.append({
                "plugin_id": plugin_id,
                "title": title,
                "path": path,
                "frontend_url": frontend_url,
            })
    return entries

async def _install_plugin_from_zip(
    temp_path: str,
    tenant_id: str,
    *,
    expected_package_sha256: str | None = None,
    expected_package_signature: str | None = None,
):
    """从 ZIP 安装插件（核心逻辑）。"""
    app_env = str(settings.APP_ENV or "dev").strip().lower()
    sig_required = settings.PLUGIN_PACKAGE_SIGNATURE_REQUIRED
    prod_default_required = settings.PLUGIN_PACKAGE_INTEGRITY_REQUIRED_IN_PROD
    enforce_required = sig_required or (app_env == "prod" and prod_default_required)
    if enforce_required and not expected_package_sha256:
        raise HTTPException(status_code=400, detail="Plugin package hash missing: please fill in package_sha256 in catalog")  # i18n
    if enforce_required and not expected_package_signature:
        raise HTTPException(status_code=400, detail="Plugin package signature missing: please fill in package_signature in catalog")  # i18n

    actual_sha: str | None = None
    if expected_package_signature:
        actual_sha = _sha256_hex_of_file(temp_path)

    if expected_package_sha256:
        if actual_sha is not None:
            if actual_sha != (expected_package_sha256 or "").strip().lower():
                raise HTTPException(status_code=400, detail="Plugin package SHA256 mismatch, install aborted")
        else:
            _verify_file_sha256(temp_path, expected_package_sha256)

    with zipfile.ZipFile(temp_path, "r") as zip_ref:
        file_list = zip_ref.namelist()

        from app.core.plugin_security_scan import scan_zip_for_security_risks, build_security_report
        security_hits = scan_zip_for_security_risks(zip_ref, file_list)
        if security_hits:
            report = build_security_report(security_hits)
            high_hits = [h for h in report.get("hits", []) if any(
                k in h for k in ["dangerous_call:", "native_api:", "deserialization:"]
            )]
            if settings.PLUGIN_SECURITY_SCAN_BLOCK_ON_HIT and high_hits:
                detail = "; ".join(security_hits[:10])
                raise HTTPException(status_code=400, detail=f"Security scan detected dangerous usage (blocked): {detail}")  # i18n
            logger.warning("Plugin package security scan hit %d risk items: %s", len(security_hits), "; ".join(security_hits[:5]))  # i18n

        if "plugin.json" not in file_list:
            raise HTTPException(status_code=400, detail="Invalid plugin package: missing plugin.json")  # i18n
        with zip_ref.open("plugin.json") as f:
            metadata = json.load(f)
            plugin_id = metadata.get("id")
        if not plugin_id:
            raise HTTPException(status_code=400, detail="Invalid plugin metadata: Missing id")  # i18n
        plugin_id = str(plugin_id).strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", plugin_id):
            raise HTTPException(status_code=400, detail="Invalid plugin id (alphanumeric, -, _, max 64 chars)")  # i18n
        ms_err = manifest_signature_install_error(metadata if isinstance(metadata, dict) else None)
        if ms_err:
            raise HTTPException(status_code=400, detail=ms_err)
        conflict_py = os.path.join(str(PLUGIN_DIR_ABS), f"{plugin_id}.py")
        if os.path.exists(conflict_py):
            raise HTTPException(status_code=400, detail=f"Plugin id conflicts with existing single-file plugin: {plugin_id}")  # i18n
        previous_version = str((plugin_manager.metadata.get(plugin_id, {}) or {}).get("version") or "").strip()
        target_dir = os.path.join(PLUGIN_DIR, plugin_id)
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        os.makedirs(target_dir)
        try:
            safe_extract_zip(zip_ref, target_dir)
        except UnsafeArchiveError as e:
            raise HTTPException(status_code=400, detail=f"Plugin package is unsafe: {e}")  # i18n
        if metadata.get("type") == "paid":
            license_data = None
            if "license.json" in file_list:
                with zip_ref.open("license.json") as f:
                    license_data = json.load(f)
            elif isinstance(metadata.get("license"), dict):
                license_data = metadata.get("license")
            if license_data:
                verify_plugin_license(metadata, license_data, tenant_id)
        _validate_plugin_menu_conflicts(metadata or {}, plugin_id)

        if expected_package_signature:
            pub = (settings.PLUGIN_PACKAGE_ED25519_PUBLIC_KEY or "").strip() or (
                settings.LICENSE_ED25519_PUBLIC_KEY or ""
            ).strip()
            if not pub:
                raise HTTPException(status_code=400, detail="Plugin package signature verification public key not configured: PLUGIN_PACKAGE_ED25519_PUBLIC_KEY / LICENSE_ED25519_PUBLIC_KEY")  # i18n
            if not actual_sha:
                actual_sha = _sha256_hex_of_file(temp_path)
            ok = verify_ed25519_signature({"package_sha256": actual_sha}, expected_package_signature, pub)
            if not ok:
                raise HTTPException(status_code=400, detail="Plugin package signature verification failed: package_signature mismatch")  # i18n

        try:
            await _ensure_plugin_dependencies_installed(plugin_id, target_dir, metadata or {}, file_list)  # 同步requests→异步httpx，避免阻塞事件循环
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Plugin dependency install failed: {e}")  # i18n
        plugin_manager.load_plugins()
        new_version = str((plugin_manager.metadata.get(plugin_id, {}) or {}).get("version") or metadata.get("version") or "").strip()
        operation = "upgrade" if previous_version else "install"
        tables_to_create = _sanitize_plugin_tables(
            metadata.get("tables"),
            plugin_id=plugin_id,
            enforce_plugin_id_prefix=settings.PLUGIN_TABLES_REQUIRE_PLUGIN_ID_PREFIX,
        )
        return {
            "status": "success",
            "plugin_id": plugin_id,
            "version": new_version or None,
            "previous_version": previous_version or None,
            "operation": operation,
            "tables": tables_to_create,
            "message": f"Plugin {plugin_id} installed successfully"
        }

def verify_plugin_license(metadata: dict, license_data: dict | None, tenant_id: str):
    if not license_data:
        raise HTTPException(status_code=403, detail="Paid plugin missing license.json")  # i18n
    plugin_id = str(metadata.get("id") or "")
    feature_code = str(metadata.get("feature_code") or plugin_id)
    valid, reason = verify_license_payload(
        license_data=license_data,
        tenant_id=tenant_id,
        plugin_id=plugin_id,
        feature_code=feature_code,
    )
    if not valid:
        raise HTTPException(status_code=403, detail=f"Plugin authorization invalid: {reason}")  # i18n

def _read_plugin_tables(plugin_id: str) -> list[str]:
    """
    在删除插件前读取 plugin.json 中的 tables 字段，返回需在卸载时删除的表名列表。
    """
    target_dir = os.path.join(PLUGIN_DIR, plugin_id)
    json_path = os.path.join(target_dir, "plugin.json")
    if not os.path.exists(json_path):
        return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        raw = meta.get("tables")
        return _sanitize_plugin_tables(raw, plugin_id=plugin_id, enforce_plugin_id_prefix=False)
    except Exception as e:
        logger.debug(f"Operation failed, returning default value: {e}")  # i18n
        return []

async def _delete_oss_plugin_runtime_config_rows(db: AsyncSession, plugin_id: str) -> None:
    """删除所有租户下该插件的运行时配置行：setting_key = plugin_runtime_config.{tenant}.{plugin_id}。"""
    pid = str(plugin_id or "").strip()
    if not pid:
        return
    suffix = "." + pid
    res = await db.execute(
        select(SystemSetting).where(SystemSetting.setting_key.startswith("plugin_runtime_config."))
    )
    for row in res.scalars().all():
        if str(row.setting_key or "").endswith(suffix):
            await db.delete(row)

async def _build_uninstall_risk_preview(db: AsyncSession, plugin_id: str) -> dict:
    """
    统一卸载风险评估。
    """
    pid = str(plugin_id or "").strip()
    tables = _read_plugin_tables(pid)
    table_count = len(tables)

    runtime_config_rows = 0
    try:
        suffix = "." + pid
        res = await db.execute(
            select(SystemSetting.setting_key).where(SystemSetting.setting_key.startswith("plugin_runtime_config."))
        )
        keys = [str(k or "") for k in res.scalars().all()]
        runtime_config_rows = sum(1 for k in keys if k.endswith(suffix))
    except Exception as e:
        logger.debug(f"Operation failed, returning default value: {e}")  # i18n
        runtime_config_rows = 0

    meta = plugin_manager.metadata.get(pid, {}) if isinstance(plugin_manager.metadata, dict) else {}
    plugin_type = str((meta or {}).get("type") or "free").strip().lower()

    warnings: list[str] = []
    if table_count > 0:
        warnings.append(f"Will delete {table_count} plugin data table(s), data cannot be recovered.")  # i18n
    if runtime_config_rows > 0:
        warnings.append(f"Will clean up {runtime_config_rows} plugin runtime config row(s).")  # i18n
    if plugin_type == "paid":
        warnings.append("This is a paid plugin, functionality will be unavailable after uninstall.")  # i18n
    if table_count == 0 and runtime_config_rows == 0:
        warnings.append("No plugin data tables or runtime config found, will only delete plugin files and menu entries.")  # i18n

    if table_count >= 3:
        risk_level = "critical"
    elif table_count > 0:
        risk_level = "high"
    elif runtime_config_rows > 0:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "plugin_id": pid,
        "risk_level": risk_level,
        "warnings": warnings,
        "tables_to_drop": tables,
        "table_count": table_count,
        "runtime_config_rows": runtime_config_rows,
        "ack_required": True,
        "ack_phrase": f"UNINSTALL {pid}",
    }

async def _ensure_oss_paid_plugin_runtime_access(
    request: Request,
    db: AsyncSession,
    current_user: User,
    plugin_id: str,
) -> None:
    """
    OSS：已加载的付费插件访问 /runtime/* 与 plugin-assets 时，需与 /menus 一致出现在已购列表（超管豁免）。
    """
    if (settings.APP_EDITION or "oss").lower() == "server":
        return
    if getattr(current_user, "is_superuser", False):
        return
    pid = str(plugin_id or "").strip()
    if not pid:
        return
    meta = plugin_manager.metadata.get(pid)
    if not isinstance(meta, dict):
        return
    if str(meta.get("type") or "").lower() != "paid":
        return

    async def _deny(status_code: int, detail: str, extra: str = "") -> None:
        await safe_auth_audit(
            db,
            module="plugins",
            action="paid_runtime_entitlement_check",
            source="plugin_runtime",
            operator=current_user.username or "unknown",
            result="failure",
            tenant_id=_audit_tid(current_user),
            status_code=status_code,
            detail=detail,
            extra_summary=(f"plugin_id={pid}; mode={mode}" + (f"; {extra}" if extra else "")),
        )
        normalized = str(detail or "").strip()
        if status_code == 402 and normalized == "SUBSCRIPTION_EXPIRED":
            raise HTTPException(status_code=402, detail=_entitlement_error_detail("SUBSCRIPTION_EXPIRED"))
        if status_code == 403 and normalized == "PLUGIN_NOT_PURCHASED":
            raise HTTPException(status_code=403, detail=_entitlement_error_detail("PLUGIN_NOT_PURCHASED"))
        raise HTTPException(status_code=status_code, detail=detail)

    mode = _resolve_paid_runtime_auth_mode()
    authorization = _authorization_for_server_proxy(request)

    if mode == "cache_only":
        pids = await get_purchased_plugin_ids_cached(request, current_user)
        if pid in pids:
            return
        await _deny(403, "PLUGIN_NOT_PURCHASED", "policy=cache_only; fallback=purchased_cache")
        return

    if mode == "online_strict":
        ok, status_code, detail = await _check_paid_plugin_entitlement_online_cached(
            request,
            current_user,
            pid,
            authorization,
            strict_response_body=True,
        )
        if ok:
            await invalidate_purchased_plugin_ids_cache_for_user(str(current_user.id))
            return
        await _deny(status_code, detail, "policy=fail_close")
        return

    if mode == "online_prefer_cache":
        pids = await get_purchased_plugin_ids_cached(request, current_user)
        if pid in pids:
            return
        ok, status_code, detail = await _check_paid_plugin_entitlement_online_cached(
            request,
            current_user,
            pid,
            authorization,
            strict_response_body=True,
        )
        if ok:
            await invalidate_purchased_plugin_ids_cache_for_user(str(current_user.id))
            return
        await _deny(status_code, detail, "policy=cache_then_online")
        return

    # online_fail_open
    ok, status_code, detail = await _check_paid_plugin_entitlement_online_cached(
        request,
        current_user,
        pid,
        authorization,
        strict_response_body=False,
    )
    if ok:
        await invalidate_purchased_plugin_ids_cache_for_user(str(current_user.id))
        return
    if status_code in (401, 402, 403):
        await _deny(status_code, detail, "policy=online_fail_open; definitive_denied=true")
        return
    pids = await get_purchased_plugin_ids_cached(request, current_user)
    if pid in pids:
        return
    await _deny(403, "PLUGIN_NOT_PURCHASED", "policy=online_fail_open; fallback_cache_miss=true")

async def require_oss_paid_runtime_from_path(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    path = request.url.path or ""
    for needle in ("/plugins/runtime/", "/plugins/plugin-assets/"):
        if needle in path:
            rest = path.split(needle, 1)[1]
            slug = rest.split("/")[0].strip()
            if slug:
                await _ensure_oss_paid_plugin_runtime_access(request, db, current_user, slug)
            return
