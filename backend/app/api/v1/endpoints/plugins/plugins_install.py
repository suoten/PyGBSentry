"""
plugins_install — 插件安装/卸载/升级相关端点。
"""

import json
import os
import shutil
import httpx  # 同步requests→异步httpx，避免阻塞事件循环

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.models.user import User
from app.db.session import get_db
from app.core.plugin_manager import (
    plugin_manager,
    HOOK_ON_SHUTDOWN,
    HOOK_ON_STARTUP,
    HOOK_ON_UPGRADE,
)
from app.services.audit_center_service import audit_center_service

from .plugins_common import (
    _uuid7_hex,
    _authorization_for_server_proxy,
    _peek_plugin_json_from_zip,
    _precheck_paid_plugin_install,
    _plan_install_or_upgrade_from_zip,
    _create_plugin_upgrade_snapshot,
    _install_plugin_from_zip,
    _notify_server_plugin_event,
    _recover_plugins_after_failed_upgrade,
    _ensure_plugin_tables_created,
    _cleanup_plugin_upgrade_snapshot,
    _invalidate_purchased_plugin_ids_cache_for_user,
    _expected_sha256_from_catalog_item,
    _expected_package_signature_from_catalog_item,
    _is_allowed_package_url,
    _ensure_oss_compatible,
    _resolve_marketplace_install_payload,
    _build_uninstall_risk_preview,
    _read_plugin_tables,
    _delete_oss_plugin_runtime_config_rows,
    MarketplaceInstallRequest,
    PLUGIN_DIR,
    settings,
    logger,
)

router = APIRouter()


@router.post("/upload")
async def upload_plugin(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    """
    Upload and install a plugin (.zip). 需登录，安装成功后上报服务器版记录。
    """
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip format is supported for plugin packages")  # i18n
    # FIX: [2026-07-16 P1] 限制插件包大小（50MB，防止 zip 炸弹 OOM）
    _MAX_PLUGIN_ZIP_BYTES = 50 * 1024 * 1024
    temp_path = f"temp_{_uuid7_hex()}_{file.filename}"
    plugin_id_for_audit = "unknown"
    op_for_audit = "install"
    version_for_audit = ""
    previous_version_for_audit = ""
    install_plan: dict = {}
    upgrade_snapshot: dict | None = None
    try:
        # FIX: [2026-07-16 P1] 流式写入并限制大小
        _written = 0
        with open(temp_path, "wb") as buffer:
            while True:
                _chunk = file.file.read(65536)
                if not _chunk:
                    break
                _written += len(_chunk)
                if _written > _MAX_PLUGIN_ZIP_BYTES:
                    buffer.close()
                    import os as _os
                    _os.unlink(temp_path)
                    raise HTTPException(status_code=413, detail=f"Plugin package too large (max {_MAX_PLUGIN_ZIP_BYTES // 1024 // 1024}MB)")
                buffer.write(_chunk)
    except HTTPException:
        raise
    except (OSError, IOError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to write plugin file: {e}") from e
    peek = _peek_plugin_json_from_zip(temp_path)
    if peek:
        await _precheck_paid_plugin_install(
            {"id": peek.get("id"), "type": peek.get("type")},
            _authorization_for_server_proxy(request),
        )  # 同步requests→异步httpx，避免阻塞事件循环
    install_plan = _plan_install_or_upgrade_from_zip(temp_path)
    plugin_id_for_audit = str(install_plan.get("plugin_id") or plugin_id_for_audit)
    op_for_audit = str(install_plan.get("operation") or op_for_audit)
    previous_version_for_audit = str(install_plan.get("current_version") or "")
    version_for_audit = str(install_plan.get("incoming_version") or "")
    upgrade_snapshot = _create_plugin_upgrade_snapshot(plugin_id_for_audit)
    try:
        # 运行时安装/升级：先停机，避免旧插件后台任务在 load_plugins 后残留/重复
        await plugin_manager.emit(HOOK_ON_SHUTDOWN)
        result = await _install_plugin_from_zip(temp_path, current_user.tenant_id or "default")  # 同步requests→异步httpx，避免阻塞事件循环
        plugin_id_for_audit = str(result.get("plugin_id") or "unknown")
        op_for_audit = str(result.get("operation") or "install")
        version_for_audit = str(result.get("version") or "")
        previous_version_for_audit = str(result.get("previous_version") or "")
        plugin_id = result.get("plugin_id", "")
        version = plugin_manager.metadata.get(plugin_id, {}).get("version") if plugin_id else None
        try:
            await _notify_server_plugin_event(
                plugin_id,
                "install",
                current_user.id,
                current_user.tenant_id or "default",
                _authorization_for_server_proxy(request),
                version,
            )  # 同步requests→异步httpx，避免阻塞事件循环
        except HTTPException as he:
            if he.status_code in (402, 403):
                await _recover_plugins_after_failed_upgrade(upgrade_snapshot)
            raise
        await audit_center_service.log(
            db=db,
            module="plugins",
            action="plugin_upgrade" if op_for_audit == "upgrade" else "plugin_install",
            operator=current_user.username or "unknown",
            result="success",
            summary=(
                f"plugin_id={plugin_id_for_audit}; "
                f"tenant_id={current_user.tenant_id or 'default'}; "
                f"source=upload; operation={op_for_audit}; "
                f"previous_version={previous_version_for_audit}; version={version_for_audit}"
            ),
        )
        await _ensure_plugin_tables_created(tables=result.get("tables") or [])
        if op_for_audit == "upgrade":
            upgrade_hook_report = await plugin_manager.emit(
                HOOK_ON_UPGRADE,
                plugin_id,
                current_user.tenant_id or "default",
                previous_version=previous_version_for_audit,
                new_version=version_for_audit,
            )
            upgrade_hook_report["hook_name"] = HOOK_ON_UPGRADE
            upgrade_hook_report["operation"] = "upgrade"
            upgrade_hook_report["strict_blocked"] = False
            result["upgrade_hook_report"] = upgrade_hook_report
            hook_failed = int(upgrade_hook_report.get("failed") or 0) > 0 or int(upgrade_hook_report.get("timeouts") or 0) > 0
            if hook_failed:
                await audit_center_service.log(
                    db=db,
                    module="plugins",
                    action="plugin_upgrade_hook_warning",
                    operator=current_user.username or "unknown",
                    result="warning",
                    summary=json.dumps(
                        {
                            "plugin_id": plugin_id_for_audit,
                            "tenant_id": current_user.tenant_id or "default",
                            "source": "upload",
                            "operation": "upgrade",
                            "hook_name": HOOK_ON_UPGRADE,
                            "failed": int(upgrade_hook_report.get("failed") or 0),
                            "timeouts": int(upgrade_hook_report.get("timeouts") or 0),
                            "strict_blocked": bool(upgrade_hook_report.get("strict_blocked")),
                            "errors": upgrade_hook_report.get("errors") or [],
                        },
                        ensure_ascii=False,
                    ),
                )
                if settings.PLUGIN_UPGRADE_HOOK_STRICT:
                    upgrade_hook_report["strict_blocked"] = True
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "message": "Upgrade migration callback failed (strict mode blocked)",  # i18n
                            "strict_blocked": True,
                            "upgrade_hook_report": upgrade_hook_report,
                        },
                    )
        # 建表完成后再启动插件，确保 on_startup 可用
        await plugin_manager.emit(HOOK_ON_STARTUP)
        await _invalidate_purchased_plugin_ids_cache_for_user(current_user.id)
        _cleanup_plugin_upgrade_snapshot(upgrade_snapshot or {})
        return result
    except HTTPException as he:
        await audit_center_service.log(
            db=db,
            module="plugins",
            action="plugin_install",
            operator=current_user.username or "unknown",
            result="failed",
            summary=(
                f"plugin_id={plugin_id_for_audit}; "
                f"tenant_id={current_user.tenant_id or 'default'}; "
                f"source=upload; operation={op_for_audit}; "
                f"status_code={he.status_code}; detail={he.detail}"
            ),
        )
        await _recover_plugins_after_failed_upgrade(upgrade_snapshot)
        try:
            await plugin_manager.emit(HOOK_ON_STARTUP)  # 安装失败后重新启动所有插件，避免全部停止
        except Exception:
            logger.warning("Failed to restart plugins after install failure")
        raise he
    except Exception as e:
        await audit_center_service.log(
            db=db,
            module="plugins",
            action="plugin_install",
            operator=current_user.username or "unknown",
            result="failed",
            summary=(
                f"plugin_id={plugin_id_for_audit}; "
                f"tenant_id={current_user.tenant_id or 'default'}; "
                f"source=upload; operation={op_for_audit}; error={e}"
            ),
        )
        await _recover_plugins_after_failed_upgrade(upgrade_snapshot)
        try:
            await plugin_manager.emit(HOOK_ON_STARTUP)  # 安装失败后重新启动所有插件，避免全部停止
        except Exception:
            logger.warning("Failed to restart plugins after install failure")
        raise HTTPException(status_code=500, detail=f"Installation failed: {str(e)}")  # i18n
    finally:
        _cleanup_plugin_upgrade_snapshot(upgrade_snapshot or {})
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/marketplace/install")
async def install_from_marketplace(
    request: Request,
    payload: MarketplaceInstallRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    从商城安装插件。需登录，安装成功后上报服务器版验证并记录购买、安装记录。
    """
    plugin_payload: dict | None = None
    if payload.package_url:
        if not _is_allowed_package_url(payload.package_url):
            raise HTTPException(status_code=400, detail="Package URL domain is not allowed")  # i18n
        plugin_payload = {"id": payload.plugin_id, "package_url": payload.package_url}
    else:
        plugin_payload = await _resolve_marketplace_install_payload(payload.plugin_id)  # 同步requests→异步httpx，避免阻塞事件循环
    await _precheck_paid_plugin_install(plugin_payload or {}, _authorization_for_server_proxy(request))  # 同步requests→异步httpx，避免阻塞事件循环
    if plugin_payload:
        _ensure_oss_compatible(plugin_payload)
    expected_sha = _expected_sha256_from_catalog_item(plugin_payload or {})
    expected_sig = _expected_package_signature_from_catalog_item(plugin_payload or {})
    package_url = plugin_payload.get("package_url")
    if not package_url:
        raise HTTPException(status_code=400, detail="package_url missing")
    if not _is_allowed_package_url(package_url):
        raise HTTPException(status_code=400, detail="Package URL domain is not allowed")  # i18n
    # temp_path 缩进从 raise 后移到正确位置，避免 finally 中 NameError
    temp_path = f"temp_market_{_uuid7_hex()}.zip"
    plugin_id_for_audit = str(payload.plugin_id or "unknown")
    op_for_audit = "install"
    version_for_audit = ""
    previous_version_for_audit = ""
    install_plan: dict = {}
    upgrade_snapshot: dict | None = None
    try:
        # 运行时安装/升级：先停机，避免旧插件后台任务在 load_plugins 后残留/重复
        await plugin_manager.emit(HOOK_ON_SHUTDOWN)
        # 同步requests.get→异步httpx，避免阻塞事件循环30秒
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(package_url)
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Download failed: {response.status_code}")  # i18n
        with open(temp_path, "wb") as f:
            f.write(response.content)
        install_plan = _plan_install_or_upgrade_from_zip(temp_path, expected_plugin_id=str(payload.plugin_id or "").strip() or None)
        plugin_id_for_audit = str(install_plan.get("plugin_id") or plugin_id_for_audit)
        op_for_audit = str(install_plan.get("operation") or op_for_audit)
        previous_version_for_audit = str(install_plan.get("current_version") or "")
        version_for_audit = str(install_plan.get("incoming_version") or "")
        upgrade_snapshot = _create_plugin_upgrade_snapshot(plugin_id_for_audit)
        result = await _install_plugin_from_zip(
            temp_path,
            current_user.tenant_id or "default",
            expected_package_sha256=expected_sha,
            expected_package_signature=expected_sig,
        )  # 同步requests→异步httpx，避免阻塞事件循环
        plugin_id_for_audit = str(result.get("plugin_id") or plugin_id_for_audit)
        op_for_audit = str(result.get("operation") or "install")
        version_for_audit = str(result.get("version") or "")
        previous_version_for_audit = str(result.get("previous_version") or "")
        plugin_id = result.get("plugin_id", payload.plugin_id)
        version = plugin_payload.get("version") or (plugin_manager.metadata.get(plugin_id, {}).get("version") if plugin_id else None)
        try:
            await _notify_server_plugin_event(
                plugin_id,
                "install",
                current_user.id,
                current_user.tenant_id or "default",
                _authorization_for_server_proxy(request),
                version,
            )  # 同步requests→异步httpx，避免阻塞事件循环
        except HTTPException as he:
            if he.status_code in (402, 403):
                await _recover_plugins_after_failed_upgrade(upgrade_snapshot)
            raise
        await audit_center_service.log(
            db=db,
            module="plugins",
            action="plugin_upgrade" if op_for_audit == "upgrade" else "plugin_install",
            operator=current_user.username or "unknown",
            result="success",
            summary=(
                f"plugin_id={plugin_id_for_audit}; "
                f"tenant_id={current_user.tenant_id or 'default'}; "
                f"source=marketplace; operation={op_for_audit}; "
                f"previous_version={previous_version_for_audit}; version={version_for_audit}"
            ),
        )
        await _ensure_plugin_tables_created(tables=result.get("tables") or [])
        if op_for_audit == "upgrade":
            upgrade_hook_report = await plugin_manager.emit(
                HOOK_ON_UPGRADE,
                plugin_id,
                current_user.tenant_id or "default",
                previous_version=previous_version_for_audit,
                new_version=version_for_audit,
            )
            upgrade_hook_report["hook_name"] = HOOK_ON_UPGRADE
            upgrade_hook_report["operation"] = "upgrade"
            upgrade_hook_report["strict_blocked"] = False
            result["upgrade_hook_report"] = upgrade_hook_report
            hook_failed = int(upgrade_hook_report.get("failed") or 0) > 0 or int(upgrade_hook_report.get("timeouts") or 0) > 0
            if hook_failed:
                await audit_center_service.log(
                    db=db,
                    module="plugins",
                    action="plugin_upgrade_hook_warning",
                    operator=current_user.username or "unknown",
                    result="warning",
                    summary=json.dumps(
                        {
                            "plugin_id": plugin_id_for_audit,
                            "tenant_id": current_user.tenant_id or "default",
                            "source": "marketplace",
                            "operation": "upgrade",
                            "hook_name": HOOK_ON_UPGRADE,
                            "failed": int(upgrade_hook_report.get("failed") or 0),
                            "timeouts": int(upgrade_hook_report.get("timeouts") or 0),
                            "strict_blocked": bool(upgrade_hook_report.get("strict_blocked")),
                            "errors": upgrade_hook_report.get("errors") or [],
                        },
                        ensure_ascii=False,
                    ),
                )
                if settings.PLUGIN_UPGRADE_HOOK_STRICT:
                    upgrade_hook_report["strict_blocked"] = True
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "message": "Upgrade migration callback failed (strict mode blocked)",  # i18n
                            "strict_blocked": True,
                            "upgrade_hook_report": upgrade_hook_report,
                        },
                    )
        # 建表完成后再启动插件，确保 on_startup 可用
        await plugin_manager.emit(HOOK_ON_STARTUP)
        await _invalidate_purchased_plugin_ids_cache_for_user(current_user.id)
        _cleanup_plugin_upgrade_snapshot(upgrade_snapshot or {})
        return result
    except HTTPException as he:
        await audit_center_service.log(
            db=db,
            module="plugins",
            action="plugin_install",
            operator=current_user.username or "unknown",
            result="failed",
            summary=(
                f"plugin_id={plugin_id_for_audit}; "
                f"tenant_id={current_user.tenant_id or 'default'}; "
                f"source=marketplace; operation={op_for_audit}; "
                f"status_code={he.status_code}; detail={he.detail}"
            ),
        )
        await _recover_plugins_after_failed_upgrade(upgrade_snapshot)
        raise
    except Exception as e:
        await audit_center_service.log(
            db=db,
            module="plugins",
            action="plugin_install",
            operator=current_user.username or "unknown",
            result="failed",
            summary=(
                f"plugin_id={plugin_id_for_audit}; "
                f"tenant_id={current_user.tenant_id or 'default'}; "
                f"source=marketplace; operation={op_for_audit}; error={e}"
            ),
        )
        await _recover_plugins_after_failed_upgrade(upgrade_snapshot)
        raise
    finally:
        _cleanup_plugin_upgrade_snapshot(upgrade_snapshot or {})
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.get("/{plugin_id}/uninstall-preview")
async def uninstall_plugin_preview(
    plugin_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("config.manage")),  # 角色检查→权限码检查
):
    """卸载前预览：结构化返回风险级别、影响范围、确认短语。"""
    pid = str(plugin_id or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="plugin_id required")
    target_dir = os.path.join(PLUGIN_DIR, pid)
    target_file = os.path.join(PLUGIN_DIR, f"{pid}.py")
    if not os.path.isdir(target_dir) and not os.path.exists(target_file):
        raise HTTPException(status_code=404, detail="Plugin not installed")  # i18n
    return await _build_uninstall_risk_preview(db, pid)


@router.delete("/{plugin_id}")
async def uninstall_plugin(
    request: Request,
    plugin_id: str,
    confirm: bool = False,
    confirm_phrase: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("config.manage")),  # 角色检查→权限码检查
):
    """
    卸载插件。需登录。
    行为：1) 删除插件文件 2) 移除菜单（load_plugins 后不再加载） 3) 删除 plugin.json 中 tables 声明的数据库表
    """
    import re
    from sqlalchemy import text
    from loguru import logger

    tenant_id = current_user.tenant_id or "default"
    preview = await _build_uninstall_risk_preview(db, plugin_id)
    expected_phrase = str(preview.get("ack_phrase") or "").strip()
    if not bool(confirm):
        raise HTTPException(status_code=400, detail=f"Uninstall is a high-risk operation, please confirm first (confirm=true, confirmation phrase: {expected_phrase})")  # i18n
    if str(confirm_phrase or "").strip() != expected_phrase:
        raise HTTPException(status_code=400, detail=f"Confirmation phrase is incorrect, please enter: {expected_phrase}")  # i18n
    target_dir = os.path.join(PLUGIN_DIR, plugin_id)
    target_file = os.path.join(PLUGIN_DIR, f"{plugin_id}.py")
    removed = False
    previous_version = str((plugin_manager.metadata.get(plugin_id, {}) or {}).get("version") or "").strip()
    # G-04: 读取插件 data_policy 策略
    plugin_meta = plugin_manager.metadata.get(plugin_id, {}) or {}
    data_policy = str(plugin_meta.get("data_policy") or "").strip().lower()
    if not data_policy:
        data_policy = str(settings.PLUGIN_UNINSTALL_DEFAULT_DATA_POLICY or "cascade_delete").strip().lower()
    if data_policy not in ("cascade_delete", "preserve", "ask"):
        data_policy = "cascade_delete"
    if data_policy == "ask" and not getattr(request.query_params, "preserve_data", None):
        preserve_data_param = str(request.query_params.get("preserve_data", "") or "").strip().lower()
        if preserve_data_param not in ("true", "false"):
            raise HTTPException(
                status_code=400,
                detail="Plugin uninstall data policy is 'ask', please explicitly choose preserve_data=true/false",  # i18n
            )
        data_policy = "preserve" if preserve_data_param == "true" else "cascade_delete"
    try:
        # 删除前先读取 tables 配置
        tables_to_drop = _read_plugin_tables(plugin_id)

        # 卸载前仅触发目标插件的停机钩子，避免影响其他正在运行的插件
        await plugin_manager.emit(HOOK_ON_SHUTDOWN, plugin_id=plugin_id)
        await plugin_manager.emit(HOOK_ON_UNINSTALL, plugin_id=plugin_id)

        if os.path.isdir(target_dir):
            shutil.rmtree(target_dir)
            removed = True
        if os.path.exists(target_file):
            os.remove(target_file)
            removed = True
        if not removed:
            raise HTTPException(status_code=404, detail="Plugin not found")

        # 重新加载插件，菜单自动移除
        plugin_manager.load_plugins()

        # 卸载后仅对仍存在的插件重新触发启动钩子（load_plugins 已重新注册所有存活插件）
        # 不再全局广播 HOOK_ON_STARTUP，避免中断其他插件的运行状态

        try:
            rt = getattr(plugin_manager, "_runtime_plugin_config", None)
            if isinstance(rt, dict):
                rt.pop(plugin_id, None)
        except Exception as e:
            logger.warning(f"Error: {e}")

        await _delete_oss_plugin_runtime_config_rows(db, plugin_id)

        # G-04: 根据 data_policy 决定是否删除插件创建的数据库表
        # W-11 MySQL DDL隐式提交，rollback无法回滚DROP TABLE；改为逐表执行+记录结果
        if data_policy == "cascade_delete":
            drop_errors = []
            dropped_tables = []
            for table_name in tables_to_drop:
                try:
                    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', str(table_name)):
                        logger.warning(f"Skipping invalid table name during plugin uninstall: {table_name}")
                        continue
                    safe_name = str(table_name).replace('"', '""')
                    await db.execute(text(f'DROP TABLE IF EXISTS "{safe_name}"'))
                    dropped_tables.append(table_name)
                except Exception as e:
                    drop_errors.append((table_name, str(e)))
                    logger.warning(f"Error dropping table {table_name}: {e}")
            if drop_errors:
                logger.warning(
                    f"Plugin uninstall DROP TABLE partial failure: dropped={dropped_tables}, errors={drop_errors}. "
                    f"Note: DDL cannot be rolled back on MySQL; tables already dropped cannot be restored."
                )
        else:
            logger.info(f"Plugin {plugin_id} uninstall data policy is {data_policy}, preserving DB tables: {tables_to_drop}")  # i18n
        try:
            await db.commit()
        except Exception:
            await db.rollback()

        await _notify_server_plugin_event(
            plugin_id,
            "uninstall",
            current_user.id,
            tenant_id,
            _authorization_for_server_proxy(request),
            None,
        )  # 同步requests→异步httpx，避免阻塞事件循环
        await audit_center_service.log(
            db=db,
            module="plugins",
            action="plugin_uninstall",
            operator=current_user.username or "unknown",
            result="success",
            summary=(
                f"plugin_id={plugin_id}; "
                f"tenant_id={tenant_id}; "
                f"source=uninstall; operation=uninstall; "
                f"previous_version={previous_version}; "
                f"risk_level={preview.get('risk_level')}; table_count={preview.get('table_count', 0)}; "
                f"runtime_config_rows={preview.get('runtime_config_rows', 0)}"
            ),
        )
        return {"status": "success", "message": f"Plugin {plugin_id} uninstalled"}
    except HTTPException as he:
        await audit_center_service.log(
            db=db,
            module="plugins",
            action="plugin_uninstall",
            operator=current_user.username or "unknown",
            result="failed",
            summary=(
                f"plugin_id={plugin_id}; "
                f"tenant_id={tenant_id}; "
                f"source=uninstall; operation=uninstall; "
                f"previous_version={previous_version}; "
                f"status_code={he.status_code}; detail={he.detail}"
            ),
        )
        raise
    except Exception as e:
        await audit_center_service.log(
            db=db,
            module="plugins",
            action="plugin_uninstall",
            operator=current_user.username or "unknown",
            result="failed",
            summary=(
                f"plugin_id={plugin_id}; "
                f"tenant_id={tenant_id}; "
                f"source=uninstall; operation=uninstall; "
                f"previous_version={previous_version}; error={e}"
            ),
        )
        raise