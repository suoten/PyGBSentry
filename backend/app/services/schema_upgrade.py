from sqlalchemy import text  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from sqlalchemy.exc import OperationalError
from app.db.session import engine
from loguru import logger
import re
import time

from app.db.base import Base
from app.db.model_registry import ensure_model_registry_loaded
from app.core.config import settings

# P1-6: SQL 标识符白名单正则，防止 f-string 拼接收列名/表名注入
_SAFE_IDENT_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')



async def _ensure_resources_asset_id_nullable():
    """
    选2：彻底不依赖设备
    - 旧库里 resources.asset_id 可能是 NOT NULL，导致没有任何 Asset 时无法创建目录节点。
    - 此处把 asset_id 迁移为允许 NULL（SQLite 需要重建 resources 表）。
    """
    dialect = (getattr(engine, "dialect", None) and engine.dialect.name) or ""
    dialect = str(dialect).lower()

    async with engine.begin() as conn:
        ensure_model_registry_loaded()
        if dialect.startswith("post"):
            # 对 postgres：直接执行 ALTER；失败忽略（允许多次执行）
            try:
                await conn.execute(text("ALTER TABLE resources ALTER COLUMN asset_id DROP NOT NULL"))
            except Exception as e:
                logger.warning(f"Failed to alter resources.asset_id nullable: {e}")
            return

        if dialect != "sqlite":
            return

        # 仅当 resources 表存在时处理（sqlite）
        tbl = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='resources'"))
        if not tbl.first():
            return

        # SQLite 检查 asset_id 是否为 NOT NULL
        info = await conn.execute(text("PRAGMA table_info(resources)"))
        rows = info.all()
        asset_info = next((r for r in rows if len(r) > 1 and r[1] == "asset_id"), None)
        if not asset_info:
            return

        # PRAGMA table_info 返回字段: cid, name, type, notnull, dflt_value, pk
        if len(asset_info) > 3 and int(asset_info[3] or 0) == 0:
            return

        logger.info("Migrate sqlite: resources.asset_id => nullable (recreate table)")
        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        await conn.execute(text("DROP TABLE IF EXISTS resources_old"))
        await conn.execute(text("ALTER TABLE resources RENAME TO resources_old"))

        # 使用模型定义重建 resources（Resource.asset_id 已改为 nullable=True）
        await conn.run_sync(Base.metadata.create_all)

        # 拷贝公共列数据（避免新旧列不完全一致导致失败）
        old_info = await conn.execute(text("PRAGMA table_info(resources_old)"))
        new_info = await conn.execute(text("PRAGMA table_info(resources)"))
        old_rows = old_info.all()
        new_rows = new_info.all()

        old_cols = [r[1] for r in old_rows if len(r) > 1]
        new_cols = {r[1] for r in new_rows if len(r) > 1}
        common_cols = [c for c in old_cols if c in new_cols]
        # P1-6: 过滤不安全的列名（理论上 PRAGMA 返回的都是合法标识符，但防御性编程）
        common_cols = [c for c in common_cols if _SAFE_IDENT_RE.match(str(c))]
        if not common_cols:
            # 理论上不应发生；兜底直接清理旧表
            await conn.execute(text("DROP TABLE IF EXISTS resources_old"))
            await conn.execute(text("PRAGMA foreign_keys=ON"))
            return

        cols_sql = ", ".join(common_cols)
        sel_sql = ", ".join(common_cols)
        await conn.execute(
            text(f"INSERT INTO resources ({cols_sql}) SELECT {sel_sql} FROM resources_old")
        )
        await conn.execute(text("DROP TABLE resources_old"))
        await conn.execute(text("PRAGMA foreign_keys=ON"))

async def ensure_business_schema():
    # noqa: C901 — This function is intentionally long: it is a one-shot schema
    # migration that must run sequentially, and splitting it into sub-functions
    # would obscure the migration ordering. Each block is guarded by IF NOT
    # EXISTS / try-except for idempotency.
    """Ensure all business tables and columns exist in the database.

    This is a monolithic schema migration function that runs at startup to
    guarantee the database schema matches the ORM models. It performs:

    1. **Column additions**: Add missing columns to existing tables
       (users, assets, resources, alarms, etc.) using ``ALTER TABLE ...
       ADD COLUMN IF NOT EXISTS``.
    2. **Index creation**: Create missing indexes for query performance.
    3. **Table creation**: Create tables that don't exist yet via
       ``Base.metadata.create_all``.
    4. **Data migration**: Migrate existing data to new column formats
       (e.g., encrypt plaintext passwords, normalize status fields).
    5. **Constraint enforcement**: Add foreign keys and unique constraints.

    The function is idempotent — every statement uses ``IF NOT EXISTS`` or
    is wrapped in ``try/except`` to allow repeated execution without errors.

    Note: The function length (~970 lines) reflects the large number of
    tables and columns in the schema. Each logical section is clearly
    commented. Future refactoring could extract per-table migration logic
    into separate functions if maintainability becomes an issue.
    """
    ensure_model_registry_loaded()
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) DEFAULT 'default'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(32) DEFAULT 'viewer'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret VARCHAR(64)",
        # Align users table with app.models.user.User fields
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_superuser BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMP",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) DEFAULT 'default'",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) DEFAULT 'default'",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS parent_gb_id VARCHAR(20)",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS civil_code VARCHAR(16)",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS node_type VARCHAR(16) DEFAULT 'channel'",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE alarms ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) DEFAULT 'default'",
        # FIX: [2026-07-04] 模型 Alarm 新增 longitude/latitude 列，移动设备报警经纬度需落库 [全栈工程师]
        "ALTER TABLE alarms ADD COLUMN IF NOT EXISTS longitude FLOAT NULL",
        "ALTER TABLE alarms ADD COLUMN IF NOT EXISTS latitude FLOAT NULL",
        "CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_users_role ON users (role)",
        "CREATE INDEX IF NOT EXISTS idx_assets_tenant_id ON assets (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_resources_tenant_id ON resources (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_resources_parent_gb_id ON resources (parent_gb_id)",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS region_parent_gb_id VARCHAR(64)",
        "CREATE INDEX IF NOT EXISTS idx_resources_region_parent_gb_id ON resources (region_parent_gb_id)",
        "CREATE INDEX IF NOT EXISTS idx_resources_civil_code ON resources (civil_code)",
        "CREATE INDEX IF NOT EXISTS idx_resources_node_type ON resources (node_type)",
        "CREATE INDEX IF NOT EXISTS idx_resources_asset_id ON resources (asset_id)",
        "CREATE INDEX IF NOT EXISTS idx_resources_status ON resources (status)",
        "CREATE INDEX IF NOT EXISTS idx_resources_created_at ON resources (created_at)",
        "CREATE INDEX IF NOT EXISTS idx_resources_updated_at ON resources (updated_at)",
        "CREATE INDEX IF NOT EXISTS idx_alarms_tenant_id ON alarms (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_alarms_time ON alarms (time)",
        "CREATE INDEX IF NOT EXISTS idx_alarms_tenant_time ON alarms (tenant_id, time)",
        "CREATE INDEX IF NOT EXISTS idx_assets_updated_at ON assets (updated_at)",
        """
        CREATE TABLE IF NOT EXISTS media_port_leases (
            id VARCHAR(32) PRIMARY KEY,
            media_server_id VARCHAR(32) NOT NULL,
            port INTEGER NOT NULL,
            stream_session_id VARCHAR(32) NULL,
            leased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(media_server_id, port)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_media_port_leases_server ON media_port_leases (media_server_id)",
        "CREATE INDEX IF NOT EXISTS idx_media_port_leases_session ON media_port_leases (stream_session_id)",
        """
        CREATE TABLE IF NOT EXISTS stream_sessions (
            id VARCHAR(32) PRIMARY KEY,
            app VARCHAR(64) NOT NULL,
            stream VARCHAR(64) NOT NULL,
            resource_id VARCHAR(32) NULL,
            asset_id VARCHAR(32) NULL,
            cascade_platform_id VARCHAR(32) NULL,
            call_id VARCHAR(128) NULL,
            from_tag VARCHAR(64) NULL,
            to_tag VARCHAR(64) NULL,
            via_branch VARCHAR(64) NULL,
            cseq INTEGER NULL,
            cascade_call_id VARCHAR(128) NULL,
            cascade_from_tag VARCHAR(64) NULL,
            cascade_to_tag VARCHAR(64) NULL,
            ssrc VARCHAR(16) NULL,
            media_server_id VARCHAR(32) NULL,
            media_ip VARCHAR(64) NULL,
            media_port INTEGER NULL,
            start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            protocol VARCHAR(10) DEFAULT 'UDP'
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_stream_sessions_call_id ON stream_sessions (call_id)",
        "CREATE INDEX IF NOT EXISTS idx_stream_sessions_ssrc ON stream_sessions (ssrc)",
        "CREATE INDEX IF NOT EXISTS idx_stream_sessions_media_server ON stream_sessions (media_server_id)",
        "CREATE INDEX IF NOT EXISTS idx_stream_sessions_cascade_platform_id ON stream_sessions (cascade_platform_id)",
        "ALTER TABLE stream_sessions ADD COLUMN IF NOT EXISTS media_ip VARCHAR(64) NULL",
        "ALTER TABLE stream_sessions ADD COLUMN IF NOT EXISTS media_port INTEGER NULL",
        "ALTER TABLE stream_sessions ADD COLUMN IF NOT EXISTS media_port_lease_id VARCHAR(32) NULL",
        "ALTER TABLE stream_sessions ADD COLUMN IF NOT EXISTS cascade_platform_id VARCHAR(32) NULL",
        "ALTER TABLE stream_sessions ADD COLUMN IF NOT EXISTS cascade_call_id VARCHAR(128) NULL",
        "ALTER TABLE stream_sessions ADD COLUMN IF NOT EXISTS cascade_from_tag VARCHAR(64) NULL",
        "ALTER TABLE stream_sessions ADD COLUMN IF NOT EXISTS cascade_to_tag VARCHAR(64) NULL",
        # StreamSession tenant_id列迁移
        "ALTER TABLE stream_sessions ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) DEFAULT 'default'",
        "CREATE INDEX IF NOT EXISTS ix_stream_sessions_tenant_id ON stream_sessions (tenant_id)",
        """
        CREATE TABLE IF NOT EXISTS device_record_download_tasks (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            asset_id VARCHAR(32) NOT NULL,
            resource_id VARCHAR(32) NOT NULL,
            stream_session_id VARCHAR(32) NULL,
            call_id VARCHAR(128) NULL,
            app VARCHAR(64) NOT NULL DEFAULT 'playback',
            stream VARCHAR(64) NOT NULL,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP NOT NULL,
            status VARCHAR(24) DEFAULT 'pending',
            record_ids TEXT DEFAULT '[]',
            last_error TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_device_record_download_tasks_tenant_id ON device_record_download_tasks (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_device_record_download_tasks_asset_id ON device_record_download_tasks (asset_id)",
        "CREATE INDEX IF NOT EXISTS idx_device_record_download_tasks_resource_id ON device_record_download_tasks (resource_id)",
        "CREATE INDEX IF NOT EXISTS idx_device_record_download_tasks_call_id ON device_record_download_tasks (call_id)",
        "CREATE INDEX IF NOT EXISTS idx_device_record_download_tasks_status ON device_record_download_tasks (status)",
        """
        CREATE TABLE IF NOT EXISTS device_subscriptions (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            asset_id VARCHAR(32) NOT NULL UNIQUE,
            catalog_cycle_seconds INTEGER DEFAULT 0,
            last_catalog_sync_at TIMESTAMP NULL,
            last_catalog_sync_ok INTEGER DEFAULT 0,
            last_catalog_sync_error VARCHAR(500) DEFAULT '',
            mobile_position_enabled INTEGER DEFAULT 0,
            mobile_position_interval_seconds INTEGER DEFAULT 60,
            mobile_position_renew_seconds INTEGER DEFAULT 300,
            last_mobile_position_subscribe_at TIMESTAMP NULL,
            last_mobile_position_subscribe_ok INTEGER DEFAULT 0,
            last_mobile_position_subscribe_error VARCHAR(500) DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "ALTER TABLE device_subscriptions ADD COLUMN IF NOT EXISTS mobile_position_enabled INTEGER DEFAULT 0",
        "ALTER TABLE device_subscriptions ADD COLUMN IF NOT EXISTS mobile_position_interval_seconds INTEGER DEFAULT 60",
        "ALTER TABLE device_subscriptions ADD COLUMN IF NOT EXISTS mobile_position_renew_seconds INTEGER DEFAULT 300",
        "ALTER TABLE device_subscriptions ADD COLUMN IF NOT EXISTS last_mobile_position_subscribe_at TIMESTAMP NULL",
        "ALTER TABLE device_subscriptions ADD COLUMN IF NOT EXISTS last_mobile_position_subscribe_ok INTEGER DEFAULT 0",
        "ALTER TABLE device_subscriptions ADD COLUMN IF NOT EXISTS last_mobile_position_subscribe_error VARCHAR(500) DEFAULT ''",
        "CREATE INDEX IF NOT EXISTS idx_device_subscriptions_tenant_id ON device_subscriptions (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_device_subscriptions_asset_id ON device_subscriptions (asset_id)",
        """
        CREATE TABLE IF NOT EXISTS platform_subscriptions (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            platform_id VARCHAR(32) NOT NULL,
            event VARCHAR(64) NOT NULL,
            expires_seconds INTEGER DEFAULT 0,
            expires_at TIMESTAMP NULL,
            last_subscribe_at TIMESTAMP NULL,
            last_notify_at TIMESTAMP NULL,
            last_addr VARCHAR(128) DEFAULT '',
            last_transport VARCHAR(8) DEFAULT '',
            last_call_id VARCHAR(128) DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(platform_id, event)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_platform_subscriptions_tenant_id ON platform_subscriptions (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_platform_subscriptions_platform_id ON platform_subscriptions (platform_id)",
        "CREATE INDEX IF NOT EXISTS idx_platform_subscriptions_event ON platform_subscriptions (event)",
        "CREATE INDEX IF NOT EXISTS idx_platform_subscriptions_expires_at ON platform_subscriptions (expires_at)",
        "ALTER TABLE platform_subscriptions ADD COLUMN IF NOT EXISTS remote_from_tag VARCHAR(128) DEFAULT ''",
        "ALTER TABLE platform_subscriptions ADD COLUMN IF NOT EXISTS local_to_tag VARCHAR(128) DEFAULT ''",
        "ALTER TABLE platform_subscriptions ADD COLUMN IF NOT EXISTS remote_contact VARCHAR(512) DEFAULT ''",
        "ALTER TABLE platform_subscriptions ADD COLUMN IF NOT EXISTS record_route VARCHAR(1024) DEFAULT ''",
        "ALTER TABLE platform_subscriptions ADD COLUMN IF NOT EXISTS notify_cseq INTEGER DEFAULT 1",
        """
        CREATE TABLE IF NOT EXISTS ffmpeg_cmds (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            name VARCHAR(128) NOT NULL,
            cmd_template TEXT NOT NULL,
            enabled VARCHAR(8) DEFAULT 'true',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_ffmpeg_cmds_tenant_id ON ffmpeg_cmds (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_ffmpeg_cmds_enabled ON ffmpeg_cmds (enabled)",
        """
        CREATE TABLE IF NOT EXISTS rtp_receive_tasks (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            node_id VARCHAR(32) NOT NULL,
            port INTEGER NOT NULL,
            lease_id VARCHAR(32) NULL,
            app VARCHAR(64) DEFAULT 'live',
            stream_id VARCHAR(128) NOT NULL,
            ssrc VARCHAR(64) NULL,
            tcp_mode INTEGER DEFAULT 0,
            status VARCHAR(24) DEFAULT 'running',
            last_error TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_rtp_receive_tasks_tenant_id ON rtp_receive_tasks (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_rtp_receive_tasks_node_id ON rtp_receive_tasks (node_id)",
        "CREATE INDEX IF NOT EXISTS idx_rtp_receive_tasks_stream_id ON rtp_receive_tasks (stream_id)",
        "CREATE INDEX IF NOT EXISTS idx_rtp_receive_tasks_status ON rtp_receive_tasks (status)",
        """
        CREATE TABLE IF NOT EXISTS roles (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            code VARCHAR(64) NOT NULL,
            name VARCHAR(128) NOT NULL,
            description TEXT DEFAULT '',
            permission_codes TEXT DEFAULT '',
            is_system BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_roles_tenant_id ON roles (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_roles_code ON roles (code)",
        "ALTER TABLE roles ADD COLUMN IF NOT EXISTS permission_codes TEXT DEFAULT ''",
        """
        CREATE TABLE IF NOT EXISTS work_orders (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            alarm_id VARCHAR(32) NULL,
            title VARCHAR(255) NOT NULL,
            description TEXT NULL,
            priority VARCHAR(16) DEFAULT 'medium',
            status VARCHAR(24) DEFAULT 'open',
            assignee_user_id VARCHAR(32) NULL,
            created_by_user_id VARCHAR(32) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_work_orders_tenant_id ON work_orders (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_work_orders_status ON work_orders (status)",
        "ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS category VARCHAR(32) DEFAULT 'other'",
        "CREATE INDEX IF NOT EXISTS idx_work_orders_category ON work_orders (category)",
        "ALTER TABLE access_sources ADD COLUMN IF NOT EXISTS gb_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE access_sources ADD COLUMN IF NOT EXISTS gb_id VARCHAR(64) NULL",
        "ALTER TABLE access_sources ADD COLUMN IF NOT EXISTS gb_name VARCHAR(128) NULL",
        "ALTER TABLE access_sources ADD COLUMN IF NOT EXISTS gb_parent_gb_id VARCHAR(64) NULL",
        "ALTER TABLE access_sources ADD COLUMN IF NOT EXISTS gb_resource_id VARCHAR(32) NULL",
        "CREATE INDEX IF NOT EXISTS idx_access_sources_gb_enabled ON access_sources (gb_enabled)",
        "CREATE INDEX IF NOT EXISTS idx_access_sources_gb_id ON access_sources (gb_id)",
        "CREATE INDEX IF NOT EXISTS idx_access_sources_gb_resource_id ON access_sources (gb_resource_id)",
        """
        CREATE TABLE IF NOT EXISTS billing_plans (
            id VARCHAR(32) PRIMARY KEY,
            code VARCHAR(64) UNIQUE NOT NULL,
            name VARCHAR(128) NOT NULL,
            price_monthly INTEGER DEFAULT 0,
            price_yearly INTEGER NULL,
            description TEXT NULL,
            sort_order INTEGER DEFAULT 0,
            max_devices INTEGER DEFAULT 0,
            max_channels INTEGER DEFAULT 0,
            plugin_entitlements TEXT DEFAULT '',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        # FIX: [2026-07-03] 补全 billing_plans 表缺失的列，与模型定义对齐，
        # 防止旧库升级后查询报 OperationalError: no such column: price_yearly [性能测试工程师]
        "ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS price_yearly INTEGER NULL",
        "ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS description TEXT NULL",
        "ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0",
        "ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS max_devices INTEGER DEFAULT 0",
        "ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS max_channels INTEGER DEFAULT 0",
        "ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS plugin_entitlements TEXT DEFAULT ''",
        "ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
        """
        CREATE TABLE IF NOT EXISTS tenant_subscriptions (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) UNIQUE NOT NULL,
            plan_code VARCHAR(64) NOT NULL,
            status VARCHAR(24) DEFAULT 'active',
            starts_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            trial_ends_at TIMESTAMP NULL,
            ends_at TIMESTAMP NULL,
            reminder_sent_at TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "ALTER TABLE tenant_subscriptions ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP NULL",
        "ALTER TABLE tenant_subscriptions ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMP NULL",
        "ALTER TABLE tenant_subscriptions ADD COLUMN IF NOT EXISTS machine_code VARCHAR(128) NULL",
        "ALTER TABLE tenant_subscriptions ADD COLUMN IF NOT EXISTS machine_code_registered_at DATETIME NULL",
        "ALTER TABLE tenant_subscriptions ADD COLUMN IF NOT EXISTS extra_machine_codes TEXT NULL",
        # FIX: [2026-07-04] 模型 TenantSubscription.downgrade_history（billing.py:65）在 schema_upgrade
        #      中遗漏了对应的 ALTER TABLE，导致已存在的 tenant_subscriptions 表缺少该列，init_db 在
        #      读写订阅降级历史时触发 OperationalError "no such column: downgrade_history"。
        #      根因：新增模型列时未同步补写迁移语句。修复：补齐 ALTER TABLE 语句。 [全栈工程师]
        "ALTER TABLE tenant_subscriptions ADD COLUMN IF NOT EXISTS downgrade_history JSON NULL",
        "CREATE INDEX IF NOT EXISTS idx_tenant_subscriptions_machine_code ON tenant_subscriptions (machine_code)",
        "ALTER TABLE plugin_orders ADD COLUMN IF NOT EXISTS billing_period VARCHAR(16) NULL",
        "ALTER TABLE plugin_orders ADD COLUMN IF NOT EXISTS quantity INTEGER DEFAULT 1",
        "ALTER TABLE plugin_orders ADD COLUMN IF NOT EXISTS order_type VARCHAR(24) DEFAULT 'license'",
        "ALTER TABLE plugin_orders ADD COLUMN IF NOT EXISTS upgrade_policy VARCHAR(24) NULL",
        "ALTER TABLE plugin_orders ADD COLUMN IF NOT EXISTS version_major VARCHAR(16) NULL",
        "ALTER TABLE plugin_orders ADD COLUMN IF NOT EXISTS maintenance_until DATETIME NULL",
        """
        CREATE TABLE IF NOT EXISTS tenant_branding (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) UNIQUE NOT NULL,
            product_name VARCHAR(128) DEFAULT 'PyGBSentry',
            logo_url VARCHAR(255) NULL,
            primary_color VARCHAR(16) DEFAULT '#1f2937',
            welcome_text VARCHAR(255) DEFAULT 'Welcome to PyGBSentry',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS system_settings (
            id VARCHAR(32) PRIMARY KEY,
            setting_key VARCHAR(128) UNIQUE NOT NULL,
            setting_value VARCHAR(2000) NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_system_settings_key ON system_settings (setting_key)",
        """
        CREATE TABLE IF NOT EXISTS user_api_keys (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            user_id VARCHAR(32) NOT NULL,
            name VARCHAR(128) NOT NULL,
            key_prefix VARCHAR(16) NOT NULL,
            hashed_key VARCHAR(128) NOT NULL,
            scopes TEXT DEFAULT '[]',
            allowed_ips TEXT DEFAULT '[]',
            expires_at TIMESTAMP NULL,
            is_active BOOLEAN DEFAULT TRUE,
            revoked_at TIMESTAMP NULL,
            last_used_at TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_user_api_keys_tenant_id ON user_api_keys (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys (user_id)",
        "CREATE INDEX IF NOT EXISTS idx_user_api_keys_prefix ON user_api_keys (key_prefix)",
        """
        CREATE TABLE IF NOT EXISTS platform_runtimes (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            platform_id VARCHAR(32) NOT NULL,
            data TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_platform_runtimes_tenant_id ON platform_runtimes (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_platform_runtimes_platform_id ON platform_runtimes (platform_id)",
        """
        CREATE TABLE IF NOT EXISTS config_revisions (
            id VARCHAR(32) PRIMARY KEY,
            revision INTEGER NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'published',
            content TEXT NOT NULL DEFAULT '{}',
            created_by VARCHAR(64) NOT NULL DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_config_revisions_revision ON config_revisions (revision)",
        """
        CREATE TABLE IF NOT EXISTS config_drafts (
            id VARCHAR(32) PRIMARY KEY,
            draft_id VARCHAR(32) UNIQUE NOT NULL,
            base_revision INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(24) NOT NULL DEFAULT 'editing',
            modules TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_config_drafts_draft_id ON config_drafts (draft_id)",
        "CREATE INDEX IF NOT EXISTS idx_config_drafts_updated_at ON config_drafts (updated_at)",
        """
        CREATE TABLE IF NOT EXISTS publish_records (
            id VARCHAR(32) PRIMARY KEY,
            publish_id VARCHAR(32) UNIQUE NOT NULL,
            from_revision INTEGER NOT NULL DEFAULT 0,
            to_revision INTEGER NOT NULL DEFAULT 0,
            operator VARCHAR(64) NOT NULL DEFAULT 'system',
            note TEXT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'success',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_publish_records_publish_id ON publish_records (publish_id)",
        """
        CREATE TABLE IF NOT EXISTS operation_audits (
            id VARCHAR(32) PRIMARY KEY,
            module VARCHAR(64) NOT NULL,
            action VARCHAR(64) NOT NULL,
            operator VARCHAR(64) NOT NULL DEFAULT 'unknown',
            result VARCHAR(24) NOT NULL DEFAULT 'success',
            summary TEXT NOT NULL DEFAULT '',
            tenant_id VARCHAR(36) DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_operation_audits_module ON operation_audits (module)",
        "CREATE INDEX IF NOT EXISTS idx_operation_audits_operator ON operation_audits (operator)",
        "CREATE INDEX IF NOT EXISTS idx_operation_audits_result ON operation_audits (result)",
        "CREATE INDEX IF NOT EXISTS idx_operation_audits_created_at ON operation_audits (created_at)",
        "ALTER TABLE operation_audits ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(36) DEFAULT NULL",
        """
        CREATE TABLE IF NOT EXISTS access_sources (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            name VARCHAR(128) NOT NULL,
            protocol VARCHAR(32) NOT NULL,
            host VARCHAR(128) NOT NULL,
            port INTEGER DEFAULT 0,
            username VARCHAR(128) NULL,
            password VARCHAR(255) NULL,
            path VARCHAR(512) NULL,
            stream_name VARCHAR(128) NULL,
            enabled BOOLEAN DEFAULT TRUE,
            extra JSON DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_access_sources_tenant ON access_sources (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_access_sources_protocol ON access_sources (protocol)",
        """
        CREATE TABLE IF NOT EXISTS push_channels (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            stream_name VARCHAR(128) NOT NULL,
            push_key_enabled BOOLEAN DEFAULT FALSE,
            push_key_prefix VARCHAR(16) NULL,
            hashed_push_key VARCHAR(128) NULL,
            gb_enabled BOOLEAN DEFAULT FALSE,
            gb_resource_id VARCHAR(32) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_push_channels_tenant ON push_channels (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_push_channels_stream_name ON push_channels (stream_name)",
        "CREATE INDEX IF NOT EXISTS idx_push_channels_key_prefix ON push_channels (push_key_prefix)",
        "CREATE INDEX IF NOT EXISTS idx_push_channels_gb_resource_id ON push_channels (gb_resource_id)",
        """
        CREATE TABLE IF NOT EXISTS sip_trace_events (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            trace_id VARCHAR(128) NULL,
            event VARCHAR(64) NOT NULL,
            platform_id VARCHAR(32) NULL,
            device_id VARCHAR(64) NULL,
            channel_id VARCHAR(64) NULL,
            payload TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_sip_trace_events_tenant ON sip_trace_events (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_sip_trace_events_trace_id ON sip_trace_events (trace_id)",
        "CREATE INDEX IF NOT EXISTS idx_sip_trace_events_event ON sip_trace_events (event)",
        "CREATE INDEX IF NOT EXISTS idx_sip_trace_events_platform_id ON sip_trace_events (platform_id)",
        "CREATE INDEX IF NOT EXISTS idx_sip_trace_events_device_id ON sip_trace_events (device_id)",
        "CREATE INDEX IF NOT EXISTS idx_sip_trace_events_channel_id ON sip_trace_events (channel_id)",
        "CREATE INDEX IF NOT EXISTS idx_sip_trace_events_created_at ON sip_trace_events (created_at)",
        """
        CREATE TABLE IF NOT EXISTS media_nodes (
            id VARCHAR(32) PRIMARY KEY,
            ip VARCHAR(64) NOT NULL,
            public_ip VARCHAR(64) NULL,
            stream_ip VARCHAR(128) NULL,
            hook_base_url VARCHAR(255) NULL,
            hook_ip VARCHAR(64) NULL,
            sdp_ip VARCHAR(64) NULL,
            http_port INTEGER DEFAULT 80,
            https_port INTEGER DEFAULT 0,
            rtsp_port INTEGER DEFAULT 554,
            rtsps_port INTEGER DEFAULT 0,
            rtmp_port INTEGER DEFAULT 1935,
            rtmps_port INTEGER DEFAULT 0,
            rtp_proxy_port INTEGER DEFAULT 10000,
            rtp_port_mode VARCHAR(16) DEFAULT 'single',
            rtp_port_range_start INTEGER DEFAULT 0,
            rtp_port_range_end INTEGER DEFAULT 0,
            record_mgr_port INTEGER DEFAULT 0,
            record_file_second INTEGER DEFAULT 0,
            record_sample_ms INTEGER DEFAULT 0,
            protocol_mp4_max_second INTEGER DEFAULT 0,
            secret VARCHAR(64) NOT NULL,
            zlm_ssl_merged_pem TEXT NULL,
            is_online BOOLEAN DEFAULT FALSE,
            load FLOAT DEFAULT 0,
            last_seen_at TIMESTAMP NULL,
            last_probe_error VARCHAR(512) NULL,
            is_embedded BOOLEAN DEFAULT FALSE,
            auto_config_enabled BOOLEAN DEFAULT FALSE
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_media_nodes_ip ON media_nodes (ip)",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS stream_ip VARCHAR(128) NULL",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS hook_base_url VARCHAR(255) NULL",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS hook_ip VARCHAR(64) NULL",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS sdp_ip VARCHAR(64) NULL",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS https_port INTEGER DEFAULT 0",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS rtsps_port INTEGER DEFAULT 0",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS rtmps_port INTEGER DEFAULT 0",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS rtp_port_mode VARCHAR(16) DEFAULT 'single'",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS rtp_port_range_start INTEGER DEFAULT 0",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS rtp_port_range_end INTEGER DEFAULT 0",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS record_mgr_port INTEGER DEFAULT 0",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS record_file_second INTEGER DEFAULT 0",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS record_sample_ms INTEGER DEFAULT 0",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS protocol_mp4_max_second INTEGER DEFAULT 0",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS auto_config_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP NULL",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS last_probe_error VARCHAR(512) NULL",
        "ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS zlm_ssl_merged_pem TEXT NULL",
        """
        CREATE TABLE IF NOT EXISTS parent_platforms (
            id VARCHAR(32) PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            server_gb_id VARCHAR(20) NOT NULL UNIQUE,
            server_ip VARCHAR(64) NOT NULL,
            server_port INTEGER DEFAULT 5060,
            transport VARCHAR(8) DEFAULT 'UDP',
            client_gb_id VARCHAR(20) NOT NULL,
            password VARCHAR(128) NULL,
            is_online BOOLEAN DEFAULT FALSE,
            register_interval INTEGER DEFAULT 3600,
            keepalive_interval INTEGER DEFAULT 60,
            enable BOOLEAN DEFAULT TRUE
        )
        """,
        "ALTER TABLE parent_platforms ADD COLUMN IF NOT EXISTS catalog_batch_size INTEGER DEFAULT 0",
        "ALTER TABLE parent_platforms ADD COLUMN IF NOT EXISTS catalog_push_delay_seconds INTEGER DEFAULT 0",
        "ALTER TABLE parent_platforms ADD COLUMN IF NOT EXISTS transport VARCHAR(8) DEFAULT 'UDP'",
        "ALTER TABLE parent_platforms ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) DEFAULT 'default'",
        "ALTER TABLE parent_platforms ADD COLUMN IF NOT EXISTS last_keepalive TIMESTAMP",
        "CREATE INDEX IF NOT EXISTS idx_parent_platforms_server_gb_id ON parent_platforms (server_gb_id)",
        "CREATE INDEX IF NOT EXISTS idx_parent_platforms_enable ON parent_platforms (enable)",
        "CREATE INDEX IF NOT EXISTS idx_parent_platforms_tenant_id ON parent_platforms (tenant_id)",
        """
        CREATE TABLE IF NOT EXISTS record_schedules (
            id VARCHAR(32) PRIMARY KEY,
            resource_id VARCHAR(32) NOT NULL,
            plan_type VARCHAR(24) DEFAULT 'timed',
            enabled BOOLEAN DEFAULT TRUE,
            time_ranges TEXT DEFAULT '[]',
            priority INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_record_schedules_resource_id ON record_schedules (resource_id)",
        "CREATE INDEX IF NOT EXISTS idx_record_schedules_plan_type ON record_schedules (plan_type)",
        """
        CREATE TABLE IF NOT EXISTS records (
            id VARCHAR(32) PRIMARY KEY,
            asset_id VARCHAR(32) NOT NULL,
            resource_id VARCHAR(32) NOT NULL,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP NOT NULL,
            duration REAL NULL,
            file_path VARCHAR(255) NOT NULL,
            file_size BIGINT DEFAULT 0,
            stream_id VARCHAR(64) NULL,
            tenant_id VARCHAR(64) DEFAULT 'default',
            record_app VARCHAR(32) NULL,
            media_node_id VARCHAR(32) NULL,
            zlm_file_path VARCHAR(512) NULL,
            url_checked_at TIMESTAMP NULL,
            url_ok BOOLEAN DEFAULT TRUE,
            url_status_code INTEGER NULL,
            url_error TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        # 旧库已有 records 表但无 tenant_id 等列时，必须先 ADD COLUMN 再建索引，否则 sqlite 报 no such column
        "ALTER TABLE records ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) DEFAULT 'default'",
        "ALTER TABLE records ADD COLUMN IF NOT EXISTS record_app VARCHAR(32) NULL",
        "ALTER TABLE records ADD COLUMN IF NOT EXISTS media_node_id VARCHAR(32) NULL",
        "ALTER TABLE records ADD COLUMN IF NOT EXISTS zlm_file_path VARCHAR(512) NULL",
        "ALTER TABLE records ADD COLUMN IF NOT EXISTS url_checked_at TIMESTAMP NULL",
        "ALTER TABLE records ADD COLUMN IF NOT EXISTS url_ok BOOLEAN DEFAULT TRUE",
        "ALTER TABLE records ADD COLUMN IF NOT EXISTS url_status_code INTEGER NULL",
        "ALTER TABLE records ADD COLUMN IF NOT EXISTS url_error TEXT NULL",
        "CREATE INDEX IF NOT EXISTS idx_records_asset_id ON records (asset_id)",
        "CREATE INDEX IF NOT EXISTS idx_records_resource_id ON records (resource_id)",
        "CREATE INDEX IF NOT EXISTS idx_records_start_time ON records (start_time)",
        "CREATE INDEX IF NOT EXISTS idx_records_created_at ON records (created_at)",
        "CREATE INDEX IF NOT EXISTS idx_records_tenant_id ON records (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_records_record_app ON records (record_app)",
        "CREATE INDEX IF NOT EXISTS idx_records_media_node_id ON records (media_node_id)",
        "CREATE INDEX IF NOT EXISTS idx_records_url_ok ON records (url_ok)",
        "CREATE INDEX IF NOT EXISTS idx_records_url_checked_at ON records (url_checked_at)",
        "CREATE INDEX IF NOT EXISTS idx_records_resource_start_time ON records (resource_id, start_time)",
        """
        CREATE TABLE IF NOT EXISTS record_schedule_runtimes (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            schedule_id VARCHAR(32) NOT NULL,
            resource_id VARCHAR(32) NOT NULL,
            forced_mode VARCHAR(8) NULL,
            forced_until TIMESTAMP NULL,
            desired_recording BOOLEAN DEFAULT FALSE,
            is_recording BOOLEAN DEFAULT FALSE,
            last_eval_at TIMESTAMP NULL,
            last_stream_seen_at TIMESTAMP NULL,
            last_action_at TIMESTAMP NULL,
            last_action VARCHAR(32) NULL,
            last_action_ok BOOLEAN DEFAULT TRUE,
            last_error TEXT NULL,
            last_media_node_id VARCHAR(32) NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_record_schedule_runtimes_tenant ON record_schedule_runtimes (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_record_schedule_runtimes_schedule ON record_schedule_runtimes (schedule_id)",
        "CREATE INDEX IF NOT EXISTS idx_record_schedule_runtimes_resource ON record_schedule_runtimes (resource_id)",
        "CREATE INDEX IF NOT EXISTS idx_record_schedule_runtimes_created_at ON record_schedule_runtimes (created_at)",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS has_audio BOOLEAN DEFAULT TRUE",
        """
        CREATE TABLE IF NOT EXISTS regions (
            id VARCHAR(32) PRIMARY KEY,
            code VARCHAR(32) UNIQUE NOT NULL,
            name VARCHAR(128) NOT NULL,
            parent_id VARCHAR(32) NULL,
            level INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_regions_parent_id ON regions (parent_id)",
        "CREATE INDEX IF NOT EXISTS idx_regions_code ON regions (code)",
        """
        CREATE TABLE IF NOT EXISTS asset_maintenances (
            id VARCHAR(32) PRIMARY KEY,
            asset_id VARCHAR(32) NOT NULL,
            maintenance_type VARCHAR(32) DEFAULT 'routine',
            maintenance_date TIMESTAMP NOT NULL,
            note TEXT NULL,
            operator VARCHAR(64) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_asset_maintenances_asset_id ON asset_maintenances (asset_id)",
        """
        CREATE TABLE IF NOT EXISTS organizations (
            id VARCHAR(32) PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            parent_id VARCHAR(32) NULL,
            tenant_id VARCHAR(64) DEFAULT 'default',
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_organizations_parent_id ON organizations (parent_id)",
        "CREATE INDEX IF NOT EXISTS idx_organizations_tenant_id ON organizations (tenant_id)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS organization_id VARCHAR(32) NULL",
        "CREATE INDEX IF NOT EXISTS idx_assets_organization_id ON assets (organization_id)",
        """
        CREATE TABLE IF NOT EXISTS alarm_link_rules (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL DEFAULT 'default',
            name VARCHAR(128) NOT NULL,
            enabled BOOLEAN DEFAULT TRUE,
            min_priority INTEGER NULL,
            max_priority INTEGER NULL,
            start_time VARCHAR(8) NULL,
            end_time VARCHAR(8) NULL,
            days VARCHAR(32) NULL,
            organization_id VARCHAR(32) NULL,
            link_record BOOLEAN DEFAULT TRUE,
            link_wall BOOLEAN DEFAULT FALSE,
            link_notify BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_alarm_link_rules_tenant_enabled ON alarm_link_rules (tenant_id, enabled)",
        "CREATE INDEX IF NOT EXISTS idx_alarm_link_rules_org ON alarm_link_rules (organization_id)",
        """
        CREATE TABLE IF NOT EXISTS platform_catalog_resources (
            id VARCHAR(32) PRIMARY KEY,
            platform_id VARCHAR(32) NOT NULL,
            resource_id VARCHAR(32) NOT NULL,
            UNIQUE(platform_id, resource_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_platform_catalog_resources_platform ON platform_catalog_resources (platform_id)",
        "CREATE INDEX IF NOT EXISTS idx_platform_catalog_resources_resource ON platform_catalog_resources (resource_id)",
        "ALTER TABLE platform_catalog_resources ADD COLUMN IF NOT EXISTS virtual_gb_id VARCHAR(64) NULL",
        "ALTER TABLE platform_catalog_resources ADD COLUMN IF NOT EXISTS virtual_name VARCHAR(128) NULL",
        "ALTER TABLE platform_catalog_resources ADD COLUMN IF NOT EXISTS virtual_parent_id VARCHAR(64) NULL",
        """
        CREATE TABLE IF NOT EXISTS device_positions (
            id VARCHAR(32) PRIMARY KEY,
            device_id VARCHAR(20) NOT NULL,
            channel_id VARCHAR(20) NULL,
            latitude FLOAT NOT NULL,
            longitude FLOAT NOT NULL,
            speed FLOAT NULL,
            direction FLOAT NULL,
            altitude FLOAT NULL,
            time TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_device_positions_device_time ON device_positions (device_id, time)",
        """
        CREATE TABLE IF NOT EXISTS map_config (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            name VARCHAR(64) DEFAULT '默认地图',
            provider VARCHAR(32) DEFAULT 'tianditu',
            api_key VARCHAR(128) NULL,
            vector_tile_url VARCHAR(512) NULL,
            center_lng FLOAT DEFAULT 116.404,
            center_lat FLOAT DEFAULT 39.915,
            zoom_level INTEGER DEFAULT 12,
            min_zoom INTEGER DEFAULT 1,
            max_zoom INTEGER DEFAULT 20,
            is_active BOOLEAN DEFAULT TRUE,
            is_default BOOLEAN DEFAULT FALSE
        )
        """,
        "ALTER TABLE map_config ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) DEFAULT 'default'",
        "ALTER TABLE map_config ADD COLUMN IF NOT EXISTS name VARCHAR(64) DEFAULT '默认地图'",
        "ALTER TABLE map_config ADD COLUMN IF NOT EXISTS vector_tile_url VARCHAR(512) NULL",
        "ALTER TABLE map_config ADD COLUMN IF NOT EXISTS min_zoom INTEGER DEFAULT 1",
        "ALTER TABLE map_config ADD COLUMN IF NOT EXISTS max_zoom INTEGER DEFAULT 20",
        "ALTER TABLE map_config ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE",
        "CREATE INDEX IF NOT EXISTS idx_map_config_tenant ON map_config (tenant_id)",
        """
        CREATE TABLE IF NOT EXISTS network_metrics (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            metric VARCHAR(32) NOT NULL,
            value INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_network_metrics_metric_time ON network_metrics (metric, created_at)",
        """
        CREATE TABLE IF NOT EXISTS alarm_notifications (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            alarm_id VARCHAR(32) NULL,
            device_id VARCHAR(32) NULL,
            channel_id VARCHAR(32) NULL,
            channel VARCHAR(16) NOT NULL,
            status VARCHAR(16) NOT NULL,
            error_message TEXT NULL,
            description VARCHAR(255) NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_alarm_notifications_tenant_id ON alarm_notifications (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_alarm_notifications_sent_at ON alarm_notifications (sent_at)",
        "CREATE INDEX IF NOT EXISTS idx_alarm_notifications_channel ON alarm_notifications (channel)",
        """
        CREATE TABLE IF NOT EXISTS app_logs (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            plugin_id VARCHAR(64) NULL,
            app_version VARCHAR(32) NULL,
            platform VARCHAR(32) NULL,
            log_type VARCHAR(32) NULL,
            message TEXT NULL,
            extra TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_app_logs_tenant_id ON app_logs (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_app_logs_created_at ON app_logs (created_at)",
        """
        CREATE TABLE IF NOT EXISTS command_instructions (
            id VARCHAR(32) PRIMARY KEY,
            session_id VARCHAR(32) NOT NULL,
            content TEXT NOT NULL,
            user_id VARCHAR(32) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_command_instructions_session ON command_instructions (session_id)",
        """
        CREATE TABLE IF NOT EXISTS command_sessions (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            alarm_id VARCHAR(32) NULL,
            title VARCHAR(255) NOT NULL,
            status VARCHAR(24) DEFAULT 'open',
            started_by_user_id VARCHAR(32) NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP NULL,
            summary TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_command_sessions_tenant ON command_sessions (tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_command_sessions_status ON command_sessions (status)",
        """
        CREATE TABLE IF NOT EXISTS command_participants (
            id VARCHAR(32) PRIMARY KEY,
            session_id VARCHAR(32) NOT NULL,
            user_id VARCHAR(32) NULL,
            username VARCHAR(64) NOT NULL,
            role VARCHAR(24) DEFAULT 'observer',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_command_participants_session ON command_participants (session_id)",
        """
        CREATE TABLE IF NOT EXISTS structured_events (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            source_plugin VARCHAR(64) NULL,
            event_type VARCHAR(32) NOT NULL,
            device_id VARCHAR(64) NULL,
            channel_id VARCHAR(64) NULL,
            event_time TIMESTAMP NOT NULL,
            payload TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_structured_events_type_time ON structured_events (event_type, event_time)",
        # GB28181 Extended Fields for Assets
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS charset VARCHAR(10) DEFAULT 'UTF-8'",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS ssrc_check BOOLEAN DEFAULT FALSE",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS geo_coord_sys VARCHAR(10) DEFAULT 'WGS84'",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS as_message_channel BOOLEAN DEFAULT FALSE",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS heartbeat_interval INTEGER DEFAULT 60",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS heartbeat_count INTEGER DEFAULT 3",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS keepalive_interval INTEGER DEFAULT 60",
        # GB28181 Extended Fields for Resources (Channels)
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS address VARCHAR(255)",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS parental INTEGER DEFAULT 0",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS safety_way INTEGER DEFAULT 0",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS register_way INTEGER DEFAULT 1",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS secrecy INTEGER DEFAULT 0",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS ip_address VARCHAR(64)",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS port INTEGER",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS password VARCHAR(64)",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS ptz_type INTEGER DEFAULT 0",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS position_type INTEGER DEFAULT 0",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS room_type INTEGER DEFAULT 0",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS use_type INTEGER DEFAULT 0",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS supply_light_type INTEGER DEFAULT 0",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS direction_type INTEGER DEFAULT 0",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS resolution VARCHAR(32)",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS business_group_id VARCHAR(64)",
        # numeric_channel_id: pre-computed SHA256-based integer for fast channel lookup
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS numeric_channel_id INTEGER",
        "CREATE INDEX IF NOT EXISTS ix_resources_numeric_channel_id ON resources (numeric_channel_id)",
    ]
    dialect = (getattr(engine, "dialect", None) and engine.dialect.name) or ""
    dialect = str(dialect).lower()
    total = len(statements)

    async with engine.begin() as conn:
        if dialect == "sqlite":
            # Avoid endless waits when sqlite file is locked by other process.
            await conn.execute(text(f"PRAGMA busy_timeout={settings.SQLITE_BUSY_TIMEOUT_MS}"))

        for idx, stmt in enumerate(statements, start=1):
            exec_stmt = stmt
            stmt_preview = " ".join(stmt.strip().split())[:120]

            # SQLite does not support `ADD COLUMN IF NOT EXISTS`.
            # We rewrite it and then ignore "duplicate column" errors.
            if dialect == "sqlite" and "ADD COLUMN IF NOT EXISTS" in exec_stmt.upper():
                exec_stmt = exec_stmt.replace("ADD COLUMN IF NOT EXISTS", "ADD COLUMN")

            # MySQL does not support `CREATE INDEX IF NOT EXISTS` (added in MySQL 8.0.29+).
            # Rewrite to remove IF NOT EXISTS and ignore "duplicate key name" errors.
            is_mysql_create_index = dialect == "mysql" and "CREATE" in exec_stmt.upper() and " INDEX " in exec_stmt.upper() and "IF NOT EXISTS" in exec_stmt.upper()
            if is_mysql_create_index:
                exec_stmt = exec_stmt.replace("IF NOT EXISTS", "").strip()

            started = time.perf_counter()
            logger.debug("Schema ensure [%s/%s] start: %s", idx, total, stmt_preview)
            try:
                await conn.execute(text(exec_stmt))
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                logger.debug("Schema ensure [%s/%s] done (%s ms)", idx, total, elapsed_ms)
            except OperationalError as e:
                if dialect == "sqlite":
                    msg = str(getattr(e, "orig", e)).lower()
                    if "duplicate column name" in msg:
                        elapsed_ms = int((time.perf_counter() - started) * 1000)
                        logger.debug(
                            "Schema ensure [%s/%s] skip duplicate column (%s ms): %s",
                            idx,
                            total,
                            elapsed_ms,
                            stmt_preview,
                        )
                        continue
                    # 列尚未 ADD 时建索引会失败；正常应靠语句顺序避免，此处兜底以免整站无法启动
                    if "no such column" in msg and "create index" in exec_stmt.strip().lower():
                        elapsed_ms = int((time.perf_counter() - started) * 1000)
                        logger.debug(
                            "Schema ensure [%s/%s] skip index (no such column, %s ms): %s",
                            idx,
                            total,
                            elapsed_ms,
                            stmt_preview,
                        )
                        continue
                    # ALTER TABLE on empty DB: table doesn't exist yet; create_all will create it later
                    if "no such table" in msg and "alter table" in exec_stmt.strip().lower():
                        elapsed_ms = int((time.perf_counter() - started) * 1000)
                        logger.debug(
                            "Schema ensure [%s/%s] skip alter table (no such table, %s ms): %s",
                            idx,
                            total,
                            elapsed_ms,
                            stmt_preview,
                        )
                        continue
                    # CREATE INDEX on non-existent table: skip similarly
                    if "no such table" in msg and "create index" in exec_stmt.strip().lower():
                        elapsed_ms = int((time.perf_counter() - started) * 1000)
                        logger.debug(
                            "Schema ensure [%s/%s] skip index (no such table, %s ms): %s",
                            idx,
                            total,
                            elapsed_ms,
                            stmt_preview,
                        )
                        continue
                # MySQL: ignore "duplicate key name" error for CREATE INDEX statements
                if is_mysql_create_index:
                    msg = str(getattr(e, "orig", e)).lower()
                    if "duplicate key name" in msg or "duplicate index name" in msg:
                        elapsed_ms = int((time.perf_counter() - started) * 1000)
                        logger.debug(
                            "Schema ensure [%s/%s] skip duplicate index (%s ms): %s",
                            idx,
                            total,
                            elapsed_ms,
                            stmt_preview,
                        )
                        continue
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                logger.exception(
                    "Schema ensure [%s/%s] failed after %s ms: %s",
                    idx,
                    total,
                    elapsed_ms,
                    stmt_preview,
                )
                raise
    logger.info("Business schema ensured")

    # 统一兜底创建所有在 model_registry 注册但尚未存在的表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 选2：resources.asset_id 允许为 NULL
    try:
        await _ensure_resources_asset_id_nullable()
    except Exception as e:
        # 不阻断启动；但如果迁移失败，后续“无设备建节点”仍可能报错
        logger.warning(f"resources.asset_id nullable migration failed: {e}")
