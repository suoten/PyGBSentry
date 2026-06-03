import asyncio
import psutil
import datetime
import logging
import os
import signal
from fastapi import APIRouter, Depends, Request, BackgroundTasks, HTTPException
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.db_compat import normalize_db_type, run_compat_checks, vendor_hint
from app.db.session import AsyncSessionLocal, get_db
from app.api import deps
from app.services.auth_audit import safe_auth_audit
from app.core.zlm_target import resolve_zlm_api_target
from app.models.user import User
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.alarm import Alarm

router = APIRouter()
STARTED_AT = datetime.datetime.now(datetime.timezone.utc)

_SELECT_REASON_LABELS = {
    "specified": "Specified Node",  # i18n
    "active": "Active Node",  # i18n
    "auto": "Auto (DB)",  # i18n
    "env_auto": "Auto (ENV)",  # i18n
    "global": "Global Fallback",  # i18n
}


import sys
import platform
import io
import zipfile
import json
from fastapi.responses import StreamingResponse

@router.get("/diagnostics/export")
async def export_diagnostics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("config.manage"))  # 角色检查→权限码检查
):
    """
    一键诊断包收集与导出工具 (A-10)
    包含环境信息、数据库连接状态、最新日志脱敏导出。
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. 环境信息
        env_info = {
            "os": platform.system(),
            "os_release": platform.release(),
            "python_version": sys.version,
            "edition": getattr(settings, "APP_EDITION", "oss"),
            "tenant_id": current_user.tenant_id,
            "uptime_seconds": int((datetime.datetime.now(datetime.timezone.utc) - STARTED_AT).total_seconds())
        }
        zf.writestr("env_info.json", json.dumps(env_info, indent=2, ensure_ascii=False))
        
        # 2. 数据库状态
        db_status = "ok"
        try:
            await db.execute(text("SELECT 1"))
        except Exception as e:
            db_status = str(e)
        zf.writestr("db_status.txt", f"DB Status: {db_status}")
        
        # 3. 日志脱敏收集
        log_file = "app.log"
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()[-1000:]
                    masked_lines = []
                    for line in lines:
                        lower_line = line.lower()
                        if "password" in lower_line or "token" in lower_line or "secret" in lower_line:
                            masked_lines.append("[MASKED SENSITIVE DATA]\n")
                        else:
                            masked_lines.append(line)
                    zf.writestr("tail_app.log", "".join(masked_lines))
            except Exception as e:
                zf.writestr("tail_app.log", f"Error reading log: {e}")
        else:
            zf.writestr("tail_app.log", "No app.log found in current working directory.")
            
    zip_buffer.seek(0)
    filename = f"pygbsentry_diag_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')}.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/x-zip-compressed",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/status")
async def get_system_status(current_user: User = Depends(deps.get_current_active_user)):
    """
    Get system status (CPU, RAM, ZLM)
    """
    # System Info
    # S-07 psutil.cpu_percent(interval=1)阻塞事件循环1秒，改为异步执行
    cpu_percent = await asyncio.to_thread(psutil.cpu_percent, 1)
    memory = psutil.virtual_memory()
    
    # ZLM Info（优先使用 DB 活动/自动节点；回退全局 MEDIA_SERVER_*）
    zlm_status = "Offline"
    zlm_streams = 0
    zlm_error = None
    zlm_host, zlm_port, zlm_secret, zlm_node_id, zlm_select_reason = await resolve_zlm_api_target()
    try:
        from app.services.zlm_stream_control import _get_zlm_client
        client = await _get_zlm_client()
        res = await client.get(
            f"http://{zlm_host}:{zlm_port}/index/api/getMediaList",
            params={"secret": zlm_secret},
            timeout=2.0
        )
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == 0:
                zlm_status = "Online"
                zlm_streams = len(data.get('data', []))
            else:
                zlm_error = f"api_code={data.get('code')}, msg={data.get('msg')}"
        else:
            zlm_error = f"http_status={res.status_code}"
    except Exception as e:
        zlm_error = str(e)

    return {
        "cpu": cpu_percent,
        "memory_used": memory.used,
        "memory_total": memory.total,
        "memory_percent": memory.percent,
        "uptime": datetime.datetime.now().isoformat(),
        "uptime_seconds": int((datetime.datetime.now(datetime.timezone.utc) - STARTED_AT).total_seconds()),
        "zlm_status": zlm_status,
        "zlm_streams": zlm_streams,
        "zlm_node_id": zlm_node_id,
        "zlm_select_reason": zlm_select_reason,
        "zlm_select_reason_label": _SELECT_REASON_LABELS.get(zlm_select_reason, zlm_select_reason),
        "zlm_target": f"{zlm_host}:{zlm_port}",
        "zlm_error": zlm_error,
    }

@router.get("/edition")
def get_edition(current_user: User = Depends(deps.get_current_active_user)):
    edition = (settings.APP_EDITION or "oss").lower()
    return {
        "edition": edition,
        "is_server": edition == "server"
    }

@router.get("/help-docs")
async def get_help_docs(current_user: User = Depends(deps.get_current_active_user)):
    base_url = (getattr(settings, "PLUGIN_MARKETPLACE_BASE_URL", None) or "").rstrip("/")
    url = f"{base_url}/api/v1/ops/help-docs/public"
    try:
        from app.services.zlm_stream_control import _get_zlm_client
        client = await _get_zlm_client()
        resp = await client.get(url, timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data
    except Exception as e:
        logger.debug(f"Non-critical operation failed: {e}")  # i18n
    
    return [
        {
            "id": "1",
            "tab_name": "Quick Start",  # i18n
            "items": [
                {
                    "title": "Deployment",  # i18n
                    "content": "Run <code>docker compose --profile prod up -d</code> under <code>editions/open-source</code> for one-click startup, or start backend and frontend separately, then access via browser and log in. See README-DOCKER.md for details."  # i18n
                },
                {
                    "title": "Setup Wizard",  # i18n
                    "content": "On first login, if the setup wizard is not completed, you will be automatically directed to the Setup Wizard page to check database and media server (ZLM) connectivity; click Complete Setup to start using the system."  # i18n
                },
                {
                    "title": "Add Device",  # i18n
                    "content": "GB28181 devices register via SIP configured in Ops Center; or add RTSP/ONVIF sources via Multi-Protocol Access."  # i18n
                },
                {
                    "title": "View Monitoring",  # i18n
                    "content": "View channels in Device List, then use Monitoring Center for split-screen preview and playback."  # i18n
                },
                {
                    "title": "Recording & Alarms",  # i18n
                    "content": "Configure recording policies in Recording Plans; view and acknowledge alarms in Alarm Center."  # i18n
                },
                {
                    "title": "Plugins",  # i18n
                    "content": "Install required plugins in Plugin Center (some are paid); after installation, fill in relevant addresses in Config Center to use."  # i18n
                }
            ]
        },
        {
            "id": "2",
            "tab_name": "FAQ",  # i18n
            "items": [
                {
                    "title": "Cannot preview video?",  # i18n
                    "content": "Please check: 1) Is the device online (Device List status); 2) Is the media node (ZLM) configured correctly and reachable in Ops Center; 3) Are ports occupied or blocked by firewall. Use Quick Diagnose in Ops Center to check database and ZLM status, and export a report."  # i18n
                },
                {
                    "title": "Cannot find recordings?",  # i18n
                    "content": "Confirm a recording plan is configured and the storage path is writable; select the correct time range and channel for playback; for device recordings, the device must support GB28181 recording search. Configure recording plans per channel and policy in Recording Plans."  # i18n
                },
                {
                    "title": "No alarm notifications?",  # i18n
                    "content": "Check in Config Center that the corresponding plugin (Feishu/TV Wall/Face·License Plate·Behavior etc.) is enabled and has the correct callback URL; after publishing config, restart the backend for changes to take effect."  # i18n
                },
                {
                    "title": "Plugin installation failed?",  # i18n
                    "content": "Check network access to the plugin marketplace; for paid plugins, purchase first in Billing Center; if menus don't appear after installation, refresh the page or re-login."  # i18n
                },
                {
                    "title": "How to enable demo mode?",  # i18n
                    "content": "Set environment variable <code>DEMO_MODE=true</code> at deployment and restart the backend; the device list will show built-in demo devices (for experience only, no real video streams)."  # i18n
                },
                {
                    "title": "Database connection failed?",  # i18n
                    "content": "Verify type, host, port, database name and credentials in Ops Center Database Config; for SQLite, confirm the path is writable. After modification, save and click Test Connection to verify."  # i18n
                },
                {
                    "title": "Media Server (ZLM) shows offline?",  # i18n
                    "content": "Confirm ZLM is running and the media node IP/port in Ops Center matches <code>config.ini</code>; Hook URL must point to this backend and be accessible by ZLM."  # i18n
                }
            ]
        },
        {
            "id": "3",
            "tab_name": "Upgrade Notes",  # i18n
            "items": [
                {
                    "title": "Pre-upgrade Preparation",  # i18n
                    "content": "Before upgrading, it is recommended to <strong>backup the database and configuration</strong> (Config Center drafts can be exported or recorded)."  # i18n
                },
                {
                    "title": "Review Changes",  # i18n
                    "content": "When upgrading from x to y, check the Release Notes or CHANGELOG for <strong>configuration changes and plugin compatibility</strong> notes."  # i18n
                },
                {
                    "title": "Docker Upgrade",  # i18n
                    "content": "If using Docker, pull the new image and run <code>docker compose --profile prod up -d</code>; database volumes will be preserved."  # i18n
                },
                {
                    "title": "Post-upgrade Issues",  # i18n
                    "content": "If plugins or menus are abnormal after upgrade, try refreshing the page, re-logging in, or reinstalling the plugin in Plugin Center."  # i18n
                }
            ]
        },
        {
            "id": "4",
            "tab_name": "Docs & Support",  # i18n
            "items": [
                {
                    "title": "Documentation",  # i18n
                    "content": "For more details, refer to the project documentation or repository README. The open-source edition provides basic features; extended capabilities are available through Plugin Center."  # i18n
                },
                {
                    "title": "Copyright & Support",  # i18n
                    "content": "© PyGBSentry · Open Source + Plugin Marketplace"  # i18n
                }
            ]
        }
    ]

@router.post("/shutdown")
async def shutdown_service(
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("config.manage"))  # 角色检查→权限码检查,
):
    tid = (current_user.tenant_id or "default").strip() or "default"
    op = current_user.username or "unknown"
    if not getattr(settings, "ENABLE_SHUTDOWN_API", False):
        await safe_auth_audit(
            db,
            module="ops",
            action="shutdown",
            source="ops_api",
            operator=op,
            result="failed",
            tenant_id=tid,
            status_code=403,
            detail="api_disabled",
        )
        raise HTTPException(status_code=403, detail="Shutdown API not enabled")  # i18n
    if getattr(settings, "SHUTDOWN_API_LOCAL_ONLY", True):
        host = (request.client.host if request.client else "") or ""
        if host not in {"127.0.0.1", "::1", "localhost"}:
            await safe_auth_audit(
                db,
                module="ops",
                action="shutdown",
                source="ops_api",
                operator=op,
                result="failed",
                tenant_id=tid,
                status_code=403,
                detail="not_local",
                extra_summary=f"client_host={host}",
            )
            raise HTTPException(status_code=403, detail="Shutdown API only allows local calls")  # i18n
    pid = os.getpid()

    def _term():
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception as e:
            logger.debug(f"Non-critical operation failed: {e}")  # i18n
            os._exit(0)

    await safe_auth_audit(
        db,
        module="ops",
        action="shutdown",
        source="ops_api",
        operator=op,
        result="success",
        tenant_id=tid,
        status_code=200,
        detail="sigterm_scheduled",
        extra_summary=f"pid={pid}",
    )
    background_tasks.add_task(_term)
    return {"ok": True, "pid": pid}

@router.get("/db-check")
async def db_check(current_user: User = Depends(deps.get_current_active_user)):
    """校验当前配置的数据库连接是否可用，并给出数据库类型与兼容性提示。"""
    db_type = normalize_db_type(getattr(settings, "DATABASE_TYPE", "postgresql"))
    db_vendor_hint = vendor_hint(db_type)
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        payload = {"status": "ok", "connected": True, "database": db_type}
        if db_vendor_hint:
            payload["vendor_hint"] = db_vendor_hint
        return payload
    except Exception as e:
        payload = {
            "status": "error",
            "connected": False,
            "database": db_type,
            "detail": str(e),
        }
        if db_vendor_hint:
            payload["vendor_hint"] = db_vendor_hint
        return payload


@router.get("/db-compat-report")
async def db_compat_report(current_user: User = Depends(deps.get_current_active_user)):
    db_type = normalize_db_type(getattr(settings, "DATABASE_TYPE", "postgresql"))
    try:
        async with AsyncSessionLocal() as session:
            conn = await session.connection()
            report = await run_compat_checks(conn, db_type)
        report["connected"] = True
        return report
    except Exception as e:
        return {
            "database": db_type,
            "connected": False,
            "summary": "error",
            "checks": [{"name": "connectivity", "ok": False, "detail": str(e)}],
            "vendor_hint": vendor_hint(db_type),
        }


@router.post("/backup")
async def create_backup(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("config.manage"))  # 角色检查→权限码检查,
):
    import tempfile
    import shutil

    db_type = normalize_db_type()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(os.getcwd(), "data", "backups")
    os.makedirs(backup_dir, exist_ok=True)

    tables_to_backup = [
        "users", "assets", "resources", "alarms", "regions",
        "organizations", "media_nodes", "billing_plans",
        "tenant_subscriptions", "tenant_branding", "plugin_orders",
        "roles", "push_channels", "platforms", "system_settings",
    ]

    sensitive_fields = {
        "users": {"hashed_password", "totp_secret"},
    }

    backup_data = {}
    for table in tables_to_backup:
        try:
            # SQL注入防护 — 使用参数化标识符引用替代字符串拼接
            safe_table = table.replace('"', '""')
            result = await db.execute(text(f'SELECT * FROM "{safe_table}"'))
            rows = result.mappings().all()
            backup_data[table] = [dict(row) for row in rows]
        except Exception as e:
            logger.warning(f"Backup table {table} failed: {e}")
            backup_data[table] = []

    for key in backup_data:
        redact_fields = sensitive_fields.get(key, set())
        for row in backup_data[key]:
            for k in list(row.keys()):
                v = row[k]
                if k in redact_fields:
                    row[k] = "***REDACTED***"
                elif isinstance(v, (datetime.datetime, datetime.date)):
                    row[k] = v.isoformat()
                elif isinstance(v, bytes):
                    row[k] = v.hex()

    backup_filename = f"pygbsentry_backup_{timestamp}.json"
    backup_path = os.path.join(backup_dir, backup_filename)
    try:
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2, default=str)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Backup write failed: {e}")  # i18n
    # 备份写入json.dump无try-catch，磁盘满/权限不足导致未捕获异常

    await safe_auth_audit(
        db,
        module="ops",
        action="backup_create",
        source="backup_api",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=(current_user.tenant_id or "default").strip() or "default",
        status_code=200,
        detail="ok",
        extra_summary=f"file={backup_filename}; tables={len(tables_to_backup)}",
    )

    return {
        "status": "ok",
        "filename": backup_filename,
        "tables": len(tables_to_backup),
        "path": backup_path,
    }


@router.get("/backup/list")
async def list_backups(
    current_user: User = Depends(deps.require_permission("config.manage"))  # 角色检查→权限码检查,
):
    backup_dir = os.path.join(os.getcwd(), "data", "backups")
    if not os.path.isdir(backup_dir):
        return {"backups": []}
    backups = []
    for f in sorted(os.listdir(backup_dir), reverse=True):
        if f.startswith("pygbsentry_backup_") and f.endswith(".json"):
            fp = os.path.join(backup_dir, f)
            stat = os.stat(fp)
            backups.append({
                "filename": f,
                "size_bytes": stat.st_size,
                "created_at": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    return {"backups": backups}


import re as _re
from loguru import logger

_SAFE_COL_RE = _re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


@router.post("/restore")
async def restore_backup(
    filename: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    backup_dir = os.path.join(os.getcwd(), "data", "backups")
    backup_path = os.path.join(backup_dir, filename)
    if not os.path.isfile(backup_path):
        raise HTTPException(status_code=404, detail="Backup file not found")
    if not filename.startswith("pygbsentry_backup_") or not filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Invalid backup filename")
    real_backup_dir = os.path.realpath(backup_dir)
    real_backup_path = os.path.realpath(backup_path)
    if not real_backup_path.startswith(real_backup_dir + os.sep) and real_backup_path != real_backup_dir:
        raise HTTPException(status_code=400, detail="Invalid backup path")  # i18n

    try:
        with open(backup_path, "r", encoding="utf-8") as f:
            backup_data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        raise HTTPException(status_code=400, detail=f"Backup file corrupted or unreadable: {e}")  # i18n
    # json.load无try-catch，损坏JSON导致500且后续DB操作无法回滚

    restored_tables = []
    # Whitelist of allowed table names to prevent SQL injection from tampered backup files
    ALLOWED_RESTORE_TABLES = {
        "users", "roles", "user_roles", "organizations", "devices", "resources",
        "alarms", "alarm_notifications", "alarm_link_rules", "work_orders",
        "media_nodes", "media_port_leases", "platforms", "platform_catalog_resources",
        "stream_sessions", "push_channels", "integration_sources",
        "record_schedules", "cloud_records", "device_positions",
        "assets", "resource_assets", "audit_logs", "system_configs",
        "plugins", "plugin_configs", "user_api_keys", "blacklist",
        "device_directories", "device_subscriptions",
    }
    for table_name, rows in backup_data.items():
        if table_name not in ALLOWED_RESTORE_TABLES:
            logger.warning(f"Skip unknown table in backup: {table_name}")
            continue
        if not isinstance(rows, list) or not rows:
            continue
        try:
            # SQL注入防护 — 白名单校验已在上层完成，DELETE使用参数化标识符
            if table_name not in ALLOWED_RESTORE_TABLES:
                continue
            safe_table = table_name.replace('"', '""')
            await db.execute(text(f'DELETE FROM "{safe_table}"'))
            columns = list(rows[0].keys())
            if not all(_SAFE_COL_RE.match(c) for c in columns):
                logger.warning(f"Skip table {table_name} with unsafe column names: {columns}")
                continue
            col_list = ", ".join(columns)
            placeholders = ", ".join([f":{c}" for c in columns])
            insert_sql = f'INSERT INTO "{safe_table}" ({col_list}) VALUES ({placeholders})'
            for row in rows:
                await db.execute(text(insert_sql), row)
            restored_tables.append(table_name)
        except Exception as e:
            logger.warning(f"Restore table {table_name} failed: {e}")

    await db.commit()

    await safe_auth_audit(
        db,
        module="ops",
        action="backup_restore",
        source="backup_api",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=(current_user.tenant_id or "default").strip() or "default",
        status_code=200,
        detail="ok",
        extra_summary=f"file={filename}; tables_restored={len(restored_tables)}",
    )

    return {
        "status": "ok",
        "filename": filename,
        "tables_restored": len(restored_tables),
        "restored_tables": restored_tables,
    }


@router.get("/stream-diagnose")
async def stream_diagnose(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),  # W29 运维端点权限校验不足，改为superuser
    node_id: str = None,
    channel_id: str = None,
):
    """
    流媒体端到端诊断，按 5 个步骤逐一检测播放链路。
    """
    import socket

    items = []
    zlm_host, zlm_port, zlm_secret, resolved_node_id, select_reason = await resolve_zlm_api_target(db, node_id=node_id)
    resolved_node_id = resolved_node_id or node_id

    # 查询通道名称（resources.name / assets.name），供诊断结果展示
    channel_name = ""
    if channel_id:
        try:
            raw_sql = text("""
                SELECT COALESCE(NULLIF(TRIM(r.name), ''), NULLIF(TRIM(a.name), ''), r.gb_id) AS channel_name
                FROM resources r
                LEFT JOIN assets a ON a.id = r.asset_id
                WHERE r.gb_id = :gb_id
                LIMIT 1
            """)
            res = await db.execute(raw_sql, {"gb_id": channel_id})
            row = res.one_or_none()
            if row:
                channel_name = str(getattr(row, "channel_name", channel_id) or channel_id)
        except Exception as e:
            logger.debug(f"Operation failed, returning default: {e}")  # i18n
            channel_name = ""
    # --- Step 1: ZLM API 连通性 ---
    zlm_reachable = False
    zlm_http_url = f"http://{zlm_host}:{zlm_port}"
    try:
        from app.services.zlm_stream_control import _get_zlm_client
        client = await _get_zlm_client()
        r = await client.get(f"{zlm_http_url}/index/api/getMediaList", params={"secret": zlm_secret}, timeout=3.0)
        zlm_reachable = r.status_code == 200
        items.append({
            "step": "zlm_api",
            "key": "zlm_ping",
            "ok": zlm_reachable,
            "title": "ZLM HTTP API Connectivity",  # i18n
            "detail": f"GET {zlm_http_url}/index/api/getMediaList → HTTP {r.status_code}" if zlm_reachable else None,
            "suggestion": "Please check if ZLM is running and MEDIA_SERVER_HTTP_PORT is correct" if not zlm_reachable else None,  # i18n
        })
    except Exception as e:
        items.append({
            "step": "zlm_api",
            "key": "zlm_ping",
            "ok": False,
            "title": "ZLM HTTP API Connectivity",  # i18n
            "detail": f"Connection to {zlm_http_url} failed: {e}",  # i18n
            "suggestion": f"Please confirm ZLM is running at {zlm_host}:{zlm_port} and the port is allowed by firewall",  # i18n
        })

    # --- Step 2: 流列表检查 ---
    streams = []
    if zlm_reachable:
        try:
            from app.services.zlm_stream_control import _get_zlm_client
            client = await _get_zlm_client()
            r = await client.get(f"{zlm_http_url}/index/api/getMediaList", params={"secret": zlm_secret}, timeout=3.0)
            data = r.json()
            streams = data.get("data") or []
            target_stream = None
            if channel_id:
                target_stream = next((s for s in streams if channel_id in (s.get("stream") or "")), None)
            stream_detail = (f"Channel '{channel_name}' ({target_stream.get('stream', '')})" if target_stream else "No channel specified or stream not found (normal)")  # i18n
            items.append({
                "step": "stream_list",
                "key": "stream_list_check",
                "ok": True,
                "title": f"ZLM Stream List ({len(streams)} streams)",  # i18n
                "detail": stream_detail,
            })
            if target_stream:
                channel_label = f"'{channel_name}'" if channel_name else ""  # i18n
                items.append({
                    "step": "stream_list",
                    "key": "target_stream_app",
                    "ok": True,
                    "title": f"Target channel {channel_label} app type: {target_stream.get('app', 'unknown')}",  # i18n
                    "detail": f"stream={target_stream.get('stream')}, schema={target_stream.get('schema')}",
                })
        except Exception as e:
            items.append({
                "step": "stream_list",
                "key": "stream_list_error",
                "ok": False,
                "title": "Failed to get stream list",  # i18n
                "detail": str(e),
                "suggestion": "ZLM API may be responding abnormally, check ZLM logs",  # i18n
            })
    else:
        items.append({
            "step": "stream_list",
            "key": "stream_list_skip",
            "ok": False,
            "title": "Stream list check (skipped, ZLM API unreachable)",  # i18n
            "suggestion": "Please fix ZLM API connectivity first",  # i18n
        })

    # --- Step 3: Hook 回调检查 ---
    hook_ok = False
    hook_url = None
    try:
        from app.models.media_node import MediaNode
        from app.api.v1.endpoints.integrations import _build_hook_base_url
        node_filter = [MediaNode.id == resolved_node_id] if resolved_node_id else [MediaNode.is_active == True]
        result = await db.execute(select(MediaNode).where(*node_filter).limit(1))
        db_node = result.scalar_one_or_none()
        hook_url = _build_hook_base_url(db_node)
        from app.services.zlm_stream_control import _get_zlm_client
        client = await _get_zlm_client()
        r = await client.head(hook_url, timeout=3.0)
        hook_ok = r.status_code < 500
        items.append({
            "step": "hook_callback",
            "key": "hook_check",
            "ok": hook_ok,
            "title": "Hook Callback URL Reachability",  # i18n
            "detail": f"Callback URL: {hook_url}\nTest result: HTTP {r.status_code} {'OK' if hook_ok else 'Failed'}",  # i18n
            "suggestion": "If 404/502 returned, check backend /api/v1/hook is working, ZLM hook URL must be accessible by this backend" if not hook_ok else None,  # i18n
        })
    except Exception as e:
        items.append({
            "step": "hook_callback",
            "key": "hook_check",
            "ok": False,
            "title": "Hook Callback URL Reachability",  # i18n
            "detail": f"Callback URL: {hook_url or '(not retrieved)'}\nError: {e}",  # i18n
            "suggestion": "Check ZLM hook config is http://127.0.0.1:8000/api/v1/hook (if co-located), and /api/v1/hook responds normally",  # i18n
        })

    # --- Step 4: 流播放可用性（直连 ZLM 检查） ---
    # 目标流信息（可能来自 ZLM 实时流，也可能只是用户输入的 channel_id）
    target_stream_info = next((s for s in streams if channel_id and channel_id in (s.get("stream") or "")), None)
    app = target_stream_info.get("app", "rtp") if target_stream_info else "rtp"
    schema = str(target_stream_info.get("schema") or "hls").strip().lower() if target_stream_info else "hls"
    stream_id = channel_id or (target_stream_info.get("stream") if target_stream_info else "test")

    # 对外地址（用于 Step 5 检查反向代理）
    play_host = zlm_host
    if resolved_node_id:
        try:
            from app.models.media_node import MediaNode
            node_result = await db.execute(select(MediaNode).where(MediaNode.id == resolved_node_id).limit(1))
            db_node4play = node_result.scalar_one_or_none()
            if db_node4play:
                play_host = db_node4play.stream_ip or db_node4play.public_ip or db_node4play.ip or zlm_host
        except Exception as e:
            logger.warning(f"Failed to query online channel name: {e}")  # i18n

    # 直连 ZLM 探测（根据实际 app 类型探测对应路径）
    # GB28181 推流通道: app=rtp, schema=rtp → /rtp/<stream>/hls.m3u8
    # 拉流/转码通道: app=live, schema=http-flv → /live/<stream>.flv
    # app=download: app=download, schema=http-flv → /download/<stream>.flv
    if app == "rtp" and schema in ("rtp", "hls", ""):
        zlm_probe_addr = f"http://{zlm_host}:{zlm_port}/rtp/{stream_id}/hls.m3u8"
    elif app == "live":
        zlm_probe_addr = f"http://{zlm_host}:{zlm_port}/live/{stream_id}.flv"
    elif app == "download":
        zlm_probe_addr = f"http://{zlm_host}:{zlm_port}/download/{stream_id}.flv"
    else:
        zlm_probe_addr = f"http://{zlm_host}:{zlm_port}/live/{stream_id}.flv"
    stream_playable = False
    stream_detail = ""
    try:
        from app.services.zlm_stream_control import _get_zlm_client
        client = await _get_zlm_client()
        r = await client.get(zlm_probe_addr, timeout=5.0, follow_redirects=True)  # S-09-01 HEAD不返回响应体，改为GET才能检查#EXTM3U内容
        if r.status_code == 200:
            content_type = r.headers.get("Content-Type", "")
            if "vnd.apple.mpegurl" in content_type or "application/x-mpegURL" in content_type or r.text.strip().startswith("#EXTM3U"):
                stream_playable = True
                stream_detail = "HTTP 200, m3u8 content valid"  # i18n
            else:
                stream_playable = r.text.strip().startswith("#EXTM3U")
                stream_detail = f"HTTP 200, Content-Type={content_type}, {('m3u8 content valid' if stream_playable else 'Content-Length=' + r.headers.get('Content-Length', '0'))}"  # i18n
        else:
            stream_detail = f"HTTP {r.status_code}"
    except Exception as ex:
        stream_detail = f"Connection failed: {ex}"  # i18n

    items.append({
        "step": "play_address",
        "key": "play_addr_check",
        "ok": stream_playable,
        "title": f"Stream Playability (schema={schema}, direct ZLM)",  # i18n
        "detail": f"Channel '{channel_name}' ({stream_id})\napp={app}, schema={schema}\nProbe URL: {zlm_probe_addr}\nProbe result: {stream_detail}",  # i18n
        "suggestion": "If direct ZLM connection failed, check if HLS is enabled in ZLM config ([hls] enable=1) and if stream is being pushed" if not stream_playable else None,  # i18n
    })

    # --- Step 5: Nginx 反向代理检查（通过公网域名访问流地址） ---
    nginx_playable = False
    nginx_detail = ""
    # 通过 play_host（公网域名）构造流地址测试反向代理（根据 app 类型选择路径）
    if play_host and play_host != zlm_host:
        if app == "rtp" and schema in ("rtp", "hls", ""):
            nginx_probe_addr = f"http://{play_host}/rtp/{stream_id}/hls.m3u8"
        elif app == "live":
            nginx_probe_addr = f"http://{play_host}/live/{stream_id}.flv"
        elif app == "download":
            nginx_probe_addr = f"http://{play_host}/download/{stream_id}.flv"
        else:
            nginx_probe_addr = f"http://{play_host}/live/{stream_id}.flv"
        try:
            from app.services.zlm_stream_control import _get_zlm_client
            client = await _get_zlm_client()
            r = await client.get(nginx_probe_addr, timeout=5.0, follow_redirects=True)  # S-09-01 HEAD不返回响应体，改为GET才能检查#EXTM3U内容
            if r.status_code == 200:
                content_type = r.headers.get("Content-Type", "")
                if "vnd.apple.mpegurl" in content_type or "application/x-mpegURL" in content_type or r.text.strip().startswith("#EXTM3U"):
                    nginx_playable = True
                    nginx_detail = "HTTP 200, m3u8 content valid"  # i18n
                else:
                    nginx_playable = r.text.strip().startswith("#EXTM3U")
                    nginx_detail = f"HTTP 200, Content-Type={content_type}, {('m3u8 content valid' if nginx_playable else 'Content-Length=' + r.headers.get('Content-Length', '0'))}"  # i18n
            else:
                nginx_detail = f"HTTP {r.status_code}"
        except Exception as ex:
            nginx_detail = f"Connection failed: {ex}"  # i18n
    else:
        nginx_detail = "Public domain not configured, skipping reverse proxy check"  # i18n

    items.append({
        "step": "nginx_proxy",
        "key": "nginx_play_check",
        "ok": nginx_playable,
        "title": "Nginx Reverse Proxy Stream Playability",  # i18n
        "detail": f"Channel '{channel_name}' ({stream_id})\nPublic stream URL: {nginx_probe_addr if play_host and play_host != zlm_host else '(public domain not configured)'}\nProbe result: {nginx_detail}",  # i18n
        "suggestion": "If reverse proxy failed, confirm nginx has /rtp/ proxy configured and reloaded, and public domain resolves correctly" if not nginx_playable and play_host != zlm_host else None,  # i18n
    })

    return {"items": items, "channel_name": channel_name, "channel_id": channel_id}


@router.get("/active-streams")
async def get_active_streams(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    node_id: str = None,
):
    """
    返回指定媒体节点当前所有活跃流（仅 app=rtp），供流媒体诊断等工具选择通道。
    """
    zlm_host, zlm_port, zlm_secret, _, _ = await resolve_zlm_api_target(db, node_id=node_id)

    try:
        from app.services.zlm_stream_control import _get_zlm_client
        client = await _get_zlm_client()
        r = await client.get(
            f"http://{zlm_host}:{zlm_port}/index/api/getMediaList",
            params={"secret": zlm_secret},
            timeout=4.0
        )
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"ZLM API returned {r.status_code}")  # i18n
        data = r.json()
        if data.get("code") != 0:
            raise HTTPException(status_code=502, detail=f"ZLM API error: {data.get('msg')}")  # i18n
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to connect to ZLM: {e}")  # i18n

    streams = data.get("data") or []

    # 批量查询通道名称（stream 即 gb_id）：直接用原始 SQL 查询 resources + assets
    gb_ids = [s.get("stream", "") for s in streams if s.get("app") == "rtp" and s.get("stream")]
    
    # 优先使用 ZLM 实时流（仅 rtp）
    rtp_streams = []
    channel_names: dict[str, str] = {}
    
    if gb_ids:
        try:
            placeholders = ", ".join([f":id_{i}" for i in range(len(gb_ids))])
            params = {f"id_{i}": gid for i, gid in enumerate(gb_ids)}
            raw_sql = text(f"""
                SELECT r.gb_id AS stream_id,
                       COALESCE(NULLIF(TRIM(r.name), ''), NULLIF(TRIM(a.name), ''), r.gb_id) AS channel_name
                FROM resources r
                LEFT JOIN assets a ON a.id = r.asset_id
                WHERE r.gb_id IN ({placeholders})
            """)
            res_result = await db.execute(raw_sql, params)
            for row in res_result.all():
                stream_id = str(getattr(row, "stream_id", "") or "")
                name = str(getattr(row, "channel_name", stream_id) or stream_id)
                channel_names[stream_id] = name
        except Exception as e:
            logger.warning(f"Failed to query channel name: {e}")  # i18n

        rtp_streams = [
            {
                "stream": s.get("stream", ""),
                "name": channel_names.get(s.get("stream", ""), s.get("stream", "")),
                "app": s.get("app", ""),
                "schema": s.get("schema", ""),
                "aliveSecond": s.get("aliveSecond", 0),
                "readerCount": s.get("readerCount", 0),
                "totalReaderCount": s.get("totalReaderCount", 0),
                "bytesSpeed": s.get("bytesSpeed", 0),
            }
            for s in streams
            if s.get("app") == "rtp"
        ]
    else:
        # ZLM 无实时流时，返回数据库中在线的通道（status = 1）
        try:
            tenant_id = current_user.tenant_id or "default"
            raw_sql = text("""
                SELECT r.gb_id AS stream_id,
                       COALESCE(NULLIF(TRIM(r.name), ''), NULLIF(TRIM(a.name), ''), r.gb_id) AS channel_name
                FROM resources r
                LEFT JOIN assets a ON a.id = r.asset_id
                WHERE r.gb_id IS NOT NULL AND r.gb_id != ''
                  AND r.tenant_id = :tenant_id
                  AND r.status = 1
                ORDER BY r.name
                LIMIT 200
            """)
            res_result = await db.execute(raw_sql, {"tenant_id": tenant_id})
            for row in res_result.all():
                stream_id = str(getattr(row, "stream_id", "") or "")
                name = str(getattr(row, "channel_name", stream_id) or stream_id)
                rtp_streams.append({
                    "stream": stream_id,
                    "name": name,
                    "app": "rtp",
                    "schema": "hls",
                    "aliveSecond": 0,
                    "readerCount": 0,
                    "totalReaderCount": 0,
                    "bytesSpeed": 0,
                })
        except Exception as e:
            logger.warning(f"Failed to query online channel name: {e}")  # i18n

    logger.info(f"active-streams: gb_ids={len(gb_ids)}, channel_names={len(channel_names)}, rtp_streams={len(rtp_streams)}")
    return {"streams": rtp_streams, "total": len(rtp_streams)}


@router.get("/diagnose-report")
async def diagnose_report(
    db=Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),  # W29 运维端点权限校验不足，改为superuser
):
    """一键诊断完整报告（供导出与扩展）。"""

    report = {
        "items": [],
        "summary": "ok",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        report["items"].append({"name": "database", "ok": True, "text": "Database connection OK"})  # i18n
    except Exception as e:
        report["items"].append({"name": "database", "ok": False, "text": f"Database error: {e}"})  # i18n
        report["summary"] = "error"
    zlm_ok = False
    zlm_streams = 0
    zlm_host, zlm_port, zlm_secret, zlm_node_id, zlm_select_reason = await resolve_zlm_api_target(db)
    try:
        from app.services.zlm_stream_control import _get_zlm_client
        client = await _get_zlm_client()
        res = await client.get(
            f"http://{zlm_host}:{zlm_port}/index/api/getMediaList",
            params={"secret": zlm_secret},
            timeout=2.0
        )
        if res.status_code == 200 and res.json().get("code") == 0:
            zlm_ok = True
            zlm_streams = len(res.json().get("data", []))
    except Exception as e:
        logger.debug(f"Non-critical operation failed: {e}")  # i18n
    report["items"].append({
        "name": "zlm",
        "ok": zlm_ok,
        "text": (
            f"Media Server (ZLM): {'online' if zlm_ok else 'offline'}, current streams: {zlm_streams}; "
            f"target: {zlm_host}:{zlm_port}; source: {zlm_select_reason}"
            + (f"; node_id={zlm_node_id}" if zlm_node_id else "")
        ),  # i18n
    })
    if not zlm_ok:
        report["summary"] = "error"
    # 端到端验证检查项（供运维按步骤执行）
    report["items"].append(
        {
            "name": "e2e_checklist",
            "ok": zlm_ok,
            "text": (
                "E2E recommended steps: 1) Add/activate media node; 2) Play & playback; 3) Proxy pull & RTMP push; "
                "4) Verify hook callbacks (on_server_keepalive/on_publish); 5) Stop stream & lease reclaim."
                + (" Ready to proceed." if zlm_ok else " Please fix ZLM offline issue first.")
            ),  # i18n
        }
    )
    # 系统资源
    cpu = await asyncio.to_thread(psutil.cpu_percent, 0.1)  # R-07 异步执行避免阻塞事件循环
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    disk_used_pct = round(disk.percent, 2)
    sys_ok = mem.percent < 90 and disk_used_pct < 95
    if not sys_ok and report["summary"] != "error":
        report["summary"] = "warn"
    report["items"].append(
        {
            "name": "system",
            "ok": sys_ok,
            "text": f"System: CPU {cpu}%, Memory {mem.percent}%, Disk used {disk_used_pct}%",  # i18n
        }
    )

    # 业务统计（按租户聚合）
    tenant_id = current_user.tenant_id or "default"
    try:
        device_total = int(
            (
                await db.execute(
                    select(func.count()).select_from(Asset).where(Asset.tenant_id == tenant_id)
                )
            ).scalar()
            or 0
        )
        device_online = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Asset)
                    .where(Asset.tenant_id == tenant_id, Asset.status == 1)
                )
            ).scalar()
            or 0
        )
        channel_total = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Resource)
                    .where(Resource.tenant_id == tenant_id)
                )
            ).scalar()
            or 0
        )
        open_alarms = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Alarm)
                    .where(Alarm.tenant_id == tenant_id, Alarm.status != 1)
                )
            ).scalar()
            or 0
        )
        report["items"].append(
            {
                "name": "business",
                "ok": True,
                "text": f"Business overview: Devices {device_total} (online {device_online}), Channels {channel_total}, Unconfirmed alarms {open_alarms}",  # i18n
            }
        )
    except Exception as e:
        logger.debug(f"Non-critical operation failed: {e}")  # i18n
        # 业务统计失败不直接标记 error，只在 items 中提示
        report["items"].append(
            {
                "name": "business",
                "ok": False,
                "text": "Business statistics query failed (does not affect core services, check database or model migration)",  # i18n
            }
        )
        if report["summary"] == "ok":
            report["summary"] = "warn"

    return report


@router.get("/cluster/health", summary="Cluster health status")
async def get_cluster_health(current_user: User = Depends(deps.get_current_active_superuser)):
    """获取集群健康状态"""
    # 实现集群健康检查API
    from app.core.redis import ha_cluster
    if not ha_cluster:
        return {"enabled": False, "message": "Cluster mode not enabled"}
    return {"enabled": True, **await ha_cluster.get_cluster_health()}
