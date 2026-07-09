"""add business schema extensions

Catch-up migration that captures all schema changes from ensure_business_schema()
in app/services/schema_upgrade.py that are NOT covered by the initial migration
4bbb649f0063.  Uses raw SQL with IF NOT EXISTS / try-except for idempotency
(PostgreSQL compatible).

Revision ID: a1b2c3d4e5f6
Revises: 4bbb649f0063
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

import logging as _logging

from alembic import op

_logger = _logging.getLogger(__name__)


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '4bbb649f0063'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _exec(stmt: str) -> None:
    """Execute a single SQL statement.

    Statements containing IF NOT EXISTS are allowed to fail silently
    (idempotent DDL). All other failures are re-raised.
    """
    try:
        op.execute(stmt)
    except Exception as exc:
        if "IF NOT EXISTS" in stmt.upper():
            _logger.warning("Alembic _exec skipped (idempotent): %s | error: %s", stmt[:120], exc)
        else:
            raise


def upgrade() -> None:
    # ────────────────────────────────────────────────────────────────
    # ALTER TABLE ADD COLUMN – users
    # ────────────────────────────────────────────────────────────────
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) DEFAULT 'default'")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(32) DEFAULT 'viewer'")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled BOOLEAN DEFAULT FALSE")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret VARCHAR(512)")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_superuser BOOLEAN DEFAULT FALSE")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMP")

    # ────────────────────────────────────────────────────────────────
    # ALTER TABLE ADD COLUMN – assets
    # ────────────────────────────────────────────────────────────────
    _exec("ALTER TABLE assets ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) DEFAULT 'default'")
    _exec("ALTER TABLE assets ADD COLUMN IF NOT EXISTS organization_id VARCHAR(32) NULL")
    _exec("ALTER TABLE assets ADD COLUMN IF NOT EXISTS charset VARCHAR(10) DEFAULT 'UTF-8'")
    _exec("ALTER TABLE assets ADD COLUMN IF NOT EXISTS ssrc_check BOOLEAN DEFAULT FALSE")
    _exec("ALTER TABLE assets ADD COLUMN IF NOT EXISTS geo_coord_sys VARCHAR(10) DEFAULT 'WGS84'")
    _exec("ALTER TABLE assets ADD COLUMN IF NOT EXISTS as_message_channel BOOLEAN DEFAULT FALSE")
    _exec("ALTER TABLE assets ADD COLUMN IF NOT EXISTS heartbeat_interval INTEGER DEFAULT 60")
    _exec("ALTER TABLE assets ADD COLUMN IF NOT EXISTS heartbeat_count INTEGER DEFAULT 3")
    _exec("ALTER TABLE assets ADD COLUMN IF NOT EXISTS keepalive_interval INTEGER DEFAULT 60")

    # ────────────────────────────────────────────────────────────────
    # ALTER TABLE ADD COLUMN – resources
    # ────────────────────────────────────────────────────────────────
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) DEFAULT 'default'")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS parent_gb_id VARCHAR(20)")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS civil_code VARCHAR(16)")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS node_type VARCHAR(16) DEFAULT 'channel'")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS region_parent_gb_id VARCHAR(64)")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS has_audio BOOLEAN DEFAULT TRUE")
    # GB28181 Extended Fields for Resources (Channels)
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS address VARCHAR(255)")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS parental INTEGER DEFAULT 0")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS safety_way INTEGER DEFAULT 0")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS register_way INTEGER DEFAULT 1")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS secrecy INTEGER DEFAULT 0")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS ip_address VARCHAR(64)")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS port INTEGER")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS password VARCHAR(64)")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS ptz_type INTEGER DEFAULT 0")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS position_type INTEGER DEFAULT 0")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS room_type INTEGER DEFAULT 0")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS use_type INTEGER DEFAULT 0")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS supply_light_type INTEGER DEFAULT 0")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS direction_type INTEGER DEFAULT 0")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS resolution VARCHAR(32)")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS business_group_id VARCHAR(64)")
    _exec("ALTER TABLE resources ADD COLUMN IF NOT EXISTS numeric_channel_id INTEGER")

    # ────────────────────────────────────────────────────────────────
    # ALTER TABLE ADD COLUMN – alarms
    # ────────────────────────────────────────────────────────────────
    _exec("ALTER TABLE alarms ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) DEFAULT 'default'")

    # ────────────────────────────────────────────────────────────────
    # Indexes – users, assets, resources, alarms
    # ────────────────────────────────────────────────────────────────
    _exec("CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_users_role ON users (role)")
    _exec("CREATE INDEX IF NOT EXISTS idx_assets_tenant_id ON assets (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_assets_organization_id ON assets (organization_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_assets_updated_at ON assets (updated_at)")
    _exec("CREATE INDEX IF NOT EXISTS idx_resources_tenant_id ON resources (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_resources_parent_gb_id ON resources (parent_gb_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_resources_region_parent_gb_id ON resources (region_parent_gb_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_resources_civil_code ON resources (civil_code)")
    _exec("CREATE INDEX IF NOT EXISTS idx_resources_node_type ON resources (node_type)")
    _exec("CREATE INDEX IF NOT EXISTS idx_resources_asset_id ON resources (asset_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_resources_status ON resources (status)")
    _exec("CREATE INDEX IF NOT EXISTS idx_resources_created_at ON resources (created_at)")
    _exec("CREATE INDEX IF NOT EXISTS idx_resources_updated_at ON resources (updated_at)")
    _exec("CREATE INDEX IF NOT EXISTS ix_resources_numeric_channel_id ON resources (numeric_channel_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_alarms_tenant_id ON alarms (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_alarms_time ON alarms (time)")
    _exec("CREATE INDEX IF NOT EXISTS idx_alarms_tenant_time ON alarms (tenant_id, time)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – media_port_leases
    # ────────────────────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS media_port_leases (
            id VARCHAR(32) PRIMARY KEY,
            media_server_id VARCHAR(32) NOT NULL,
            port INTEGER NOT NULL,
            stream_session_id VARCHAR(32) NULL,
            leased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(media_server_id, port)
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_media_port_leases_server ON media_port_leases (media_server_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_media_port_leases_session ON media_port_leases (stream_session_id)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – stream_sessions (with cascade columns)
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_stream_sessions_call_id ON stream_sessions (call_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_stream_sessions_ssrc ON stream_sessions (ssrc)")
    _exec("CREATE INDEX IF NOT EXISTS idx_stream_sessions_media_server ON stream_sessions (media_server_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_stream_sessions_cascade_platform_id ON stream_sessions (cascade_platform_id)")
    # Additional columns added incrementally
    _exec("ALTER TABLE stream_sessions ADD COLUMN IF NOT EXISTS media_ip VARCHAR(64) NULL")
    _exec("ALTER TABLE stream_sessions ADD COLUMN IF NOT EXISTS media_port INTEGER NULL")
    _exec("ALTER TABLE stream_sessions ADD COLUMN IF NOT EXISTS media_port_lease_id VARCHAR(32) NULL")
    _exec("ALTER TABLE stream_sessions ADD COLUMN IF NOT EXISTS cascade_platform_id VARCHAR(32) NULL")
    _exec("ALTER TABLE stream_sessions ADD COLUMN IF NOT EXISTS cascade_call_id VARCHAR(128) NULL")
    _exec("ALTER TABLE stream_sessions ADD COLUMN IF NOT EXISTS cascade_from_tag VARCHAR(64) NULL")
    _exec("ALTER TABLE stream_sessions ADD COLUMN IF NOT EXISTS cascade_to_tag VARCHAR(64) NULL")
    _exec("ALTER TABLE stream_sessions ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) DEFAULT 'default'")
    _exec("CREATE INDEX IF NOT EXISTS ix_stream_sessions_tenant_id ON stream_sessions (tenant_id)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – device_record_download_tasks
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_device_record_download_tasks_tenant_id ON device_record_download_tasks (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_device_record_download_tasks_asset_id ON device_record_download_tasks (asset_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_device_record_download_tasks_resource_id ON device_record_download_tasks (resource_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_device_record_download_tasks_call_id ON device_record_download_tasks (call_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_device_record_download_tasks_status ON device_record_download_tasks (status)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – device_subscriptions
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("ALTER TABLE device_subscriptions ADD COLUMN IF NOT EXISTS mobile_position_enabled INTEGER DEFAULT 0")
    _exec("ALTER TABLE device_subscriptions ADD COLUMN IF NOT EXISTS mobile_position_interval_seconds INTEGER DEFAULT 60")
    _exec("ALTER TABLE device_subscriptions ADD COLUMN IF NOT EXISTS mobile_position_renew_seconds INTEGER DEFAULT 300")
    _exec("ALTER TABLE device_subscriptions ADD COLUMN IF NOT EXISTS last_mobile_position_subscribe_at TIMESTAMP NULL")
    _exec("ALTER TABLE device_subscriptions ADD COLUMN IF NOT EXISTS last_mobile_position_subscribe_ok INTEGER DEFAULT 0")
    _exec("ALTER TABLE device_subscriptions ADD COLUMN IF NOT EXISTS last_mobile_position_subscribe_error VARCHAR(500) DEFAULT ''")
    _exec("CREATE INDEX IF NOT EXISTS idx_device_subscriptions_tenant_id ON device_subscriptions (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_device_subscriptions_asset_id ON device_subscriptions (asset_id)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – platform_subscriptions
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_platform_subscriptions_tenant_id ON platform_subscriptions (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_platform_subscriptions_platform_id ON platform_subscriptions (platform_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_platform_subscriptions_event ON platform_subscriptions (event)")
    _exec("CREATE INDEX IF NOT EXISTS idx_platform_subscriptions_expires_at ON platform_subscriptions (expires_at)")
    _exec("ALTER TABLE platform_subscriptions ADD COLUMN IF NOT EXISTS remote_from_tag VARCHAR(128) DEFAULT ''")
    _exec("ALTER TABLE platform_subscriptions ADD COLUMN IF NOT EXISTS local_to_tag VARCHAR(128) DEFAULT ''")
    _exec("ALTER TABLE platform_subscriptions ADD COLUMN IF NOT EXISTS remote_contact VARCHAR(512) DEFAULT ''")
    _exec("ALTER TABLE platform_subscriptions ADD COLUMN IF NOT EXISTS record_route VARCHAR(1024) DEFAULT ''")
    _exec("ALTER TABLE platform_subscriptions ADD COLUMN IF NOT EXISTS notify_cseq INTEGER DEFAULT 1")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – ffmpeg_cmds
    # ────────────────────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS ffmpeg_cmds (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            name VARCHAR(128) NOT NULL,
            cmd_template TEXT NOT NULL,
            enabled VARCHAR(8) DEFAULT 'true',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_ffmpeg_cmds_tenant_id ON ffmpeg_cmds (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_ffmpeg_cmds_enabled ON ffmpeg_cmds (enabled)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – rtp_receive_tasks
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_rtp_receive_tasks_tenant_id ON rtp_receive_tasks (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_rtp_receive_tasks_node_id ON rtp_receive_tasks (node_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_rtp_receive_tasks_stream_id ON rtp_receive_tasks (stream_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_rtp_receive_tasks_status ON rtp_receive_tasks (status)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – roles (with permission_codes)
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_roles_tenant_id ON roles (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_roles_code ON roles (code)")
    _exec("ALTER TABLE roles ADD COLUMN IF NOT EXISTS permission_codes TEXT DEFAULT ''")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – work_orders
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_work_orders_tenant_id ON work_orders (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_work_orders_status ON work_orders (status)")
    _exec("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS category VARCHAR(32) DEFAULT 'other'")
    _exec("CREATE INDEX IF NOT EXISTS idx_work_orders_category ON work_orders (category)")

    # ────────────────────────────────────────────────────────────────
    # ALTER TABLE ADD COLUMN – access_sources (gb_enabled columns)
    # ────────────────────────────────────────────────────────────────
    _exec("ALTER TABLE access_sources ADD COLUMN IF NOT EXISTS gb_enabled BOOLEAN DEFAULT FALSE")
    _exec("ALTER TABLE access_sources ADD COLUMN IF NOT EXISTS gb_id VARCHAR(64) NULL")
    _exec("ALTER TABLE access_sources ADD COLUMN IF NOT EXISTS gb_name VARCHAR(128) NULL")
    _exec("ALTER TABLE access_sources ADD COLUMN IF NOT EXISTS gb_parent_gb_id VARCHAR(64) NULL")
    _exec("ALTER TABLE access_sources ADD COLUMN IF NOT EXISTS gb_resource_id VARCHAR(32) NULL")
    _exec("CREATE INDEX IF NOT EXISTS idx_access_sources_gb_enabled ON access_sources (gb_enabled)")
    _exec("CREATE INDEX IF NOT EXISTS idx_access_sources_gb_id ON access_sources (gb_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_access_sources_gb_resource_id ON access_sources (gb_resource_id)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – billing_plans
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    # FIX: [2026-07-03] 补全 billing_plans 缺失列，与模型定义对齐 [性能测试工程师]
    _exec("ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS price_yearly INTEGER NULL")
    _exec("ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS description TEXT NULL")
    _exec("ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0")
    _exec("ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS max_devices INTEGER DEFAULT 0")
    _exec("ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS max_channels INTEGER DEFAULT 0")
    _exec("ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS plugin_entitlements TEXT DEFAULT ''")
    _exec("ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – tenant_subscriptions
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("ALTER TABLE tenant_subscriptions ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP NULL")
    _exec("ALTER TABLE tenant_subscriptions ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMP NULL")
    _exec("ALTER TABLE tenant_subscriptions ADD COLUMN IF NOT EXISTS machine_code VARCHAR(128) NULL")
    _exec("ALTER TABLE tenant_subscriptions ADD COLUMN IF NOT EXISTS machine_code_registered_at DATETIME NULL")
    _exec("ALTER TABLE tenant_subscriptions ADD COLUMN IF NOT EXISTS extra_machine_codes TEXT NULL")
    _exec("CREATE INDEX IF NOT EXISTS idx_tenant_subscriptions_machine_code ON tenant_subscriptions (machine_code)")

    # ────────────────────────────────────────────────────────────────
    # ALTER TABLE ADD COLUMN – plugin_orders
    # ────────────────────────────────────────────────────────────────
    _exec("ALTER TABLE plugin_orders ADD COLUMN IF NOT EXISTS billing_period VARCHAR(16) NULL")
    _exec("ALTER TABLE plugin_orders ADD COLUMN IF NOT EXISTS quantity INTEGER DEFAULT 1")
    _exec("ALTER TABLE plugin_orders ADD COLUMN IF NOT EXISTS order_type VARCHAR(24) DEFAULT 'license'")
    _exec("ALTER TABLE plugin_orders ADD COLUMN IF NOT EXISTS upgrade_policy VARCHAR(24) NULL")
    _exec("ALTER TABLE plugin_orders ADD COLUMN IF NOT EXISTS version_major VARCHAR(16) NULL")
    _exec("ALTER TABLE plugin_orders ADD COLUMN IF NOT EXISTS maintenance_until DATETIME NULL")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – tenant_branding
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – system_settings
    # ────────────────────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS system_settings (
            id VARCHAR(32) PRIMARY KEY,
            setting_key VARCHAR(128) UNIQUE NOT NULL,
            setting_value VARCHAR(2000) NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_system_settings_key ON system_settings (setting_key)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – user_api_keys
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_user_api_keys_tenant_id ON user_api_keys (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys (user_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_user_api_keys_prefix ON user_api_keys (key_prefix)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – platform_runtimes
    # ────────────────────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS platform_runtimes (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            platform_id VARCHAR(32) NOT NULL,
            data TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_platform_runtimes_tenant_id ON platform_runtimes (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_platform_runtimes_platform_id ON platform_runtimes (platform_id)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – config_revisions
    # ────────────────────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS config_revisions (
            id VARCHAR(32) PRIMARY KEY,
            revision INTEGER NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'published',
            content TEXT NOT NULL DEFAULT '{}',
            created_by VARCHAR(64) NOT NULL DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_config_revisions_revision ON config_revisions (revision)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – config_drafts
    # ────────────────────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS config_drafts (
            id VARCHAR(32) PRIMARY KEY,
            draft_id VARCHAR(32) UNIQUE NOT NULL,
            base_revision INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(24) NOT NULL DEFAULT 'editing',
            modules TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_config_drafts_draft_id ON config_drafts (draft_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_config_drafts_updated_at ON config_drafts (updated_at)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – publish_records
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_publish_records_publish_id ON publish_records (publish_id)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – operation_audits
    # ────────────────────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS operation_audits (
            id VARCHAR(32) PRIMARY KEY,
            module VARCHAR(64) NOT NULL,
            action VARCHAR(64) NOT NULL,
            operator VARCHAR(64) NOT NULL DEFAULT 'unknown',
            result VARCHAR(24) NOT NULL DEFAULT 'success',
            summary TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_operation_audits_module ON operation_audits (module)")
    _exec("CREATE INDEX IF NOT EXISTS idx_operation_audits_operator ON operation_audits (operator)")
    _exec("CREATE INDEX IF NOT EXISTS idx_operation_audits_result ON operation_audits (result)")
    _exec("CREATE INDEX IF NOT EXISTS idx_operation_audits_created_at ON operation_audits (created_at)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – access_sources (with gb_enabled columns)
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_access_sources_tenant ON access_sources (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_access_sources_protocol ON access_sources (protocol)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – push_channels
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_push_channels_tenant ON push_channels (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_push_channels_stream_name ON push_channels (stream_name)")
    _exec("CREATE INDEX IF NOT EXISTS idx_push_channels_key_prefix ON push_channels (push_key_prefix)")
    _exec("CREATE INDEX IF NOT EXISTS idx_push_channels_gb_resource_id ON push_channels (gb_resource_id)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – sip_trace_events
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_sip_trace_events_tenant ON sip_trace_events (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_sip_trace_events_trace_id ON sip_trace_events (trace_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_sip_trace_events_event ON sip_trace_events (event)")
    _exec("CREATE INDEX IF NOT EXISTS idx_sip_trace_events_platform_id ON sip_trace_events (platform_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_sip_trace_events_device_id ON sip_trace_events (device_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_sip_trace_events_channel_id ON sip_trace_events (channel_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_sip_trace_events_created_at ON sip_trace_events (created_at)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – media_nodes (with extended columns)
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_media_nodes_ip ON media_nodes (ip)")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS stream_ip VARCHAR(128) NULL")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS hook_base_url VARCHAR(255) NULL")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS hook_ip VARCHAR(64) NULL")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS sdp_ip VARCHAR(64) NULL")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS https_port INTEGER DEFAULT 0")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS rtsps_port INTEGER DEFAULT 0")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS rtmps_port INTEGER DEFAULT 0")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS rtp_port_mode VARCHAR(16) DEFAULT 'single'")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS rtp_port_range_start INTEGER DEFAULT 0")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS rtp_port_range_end INTEGER DEFAULT 0")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS record_mgr_port INTEGER DEFAULT 0")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS record_file_second INTEGER DEFAULT 0")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS record_sample_ms INTEGER DEFAULT 0")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS protocol_mp4_max_second INTEGER DEFAULT 0")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS auto_config_enabled BOOLEAN DEFAULT FALSE")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP NULL")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS last_probe_error VARCHAR(512) NULL")
    _exec("ALTER TABLE media_nodes ADD COLUMN IF NOT EXISTS zlm_ssl_merged_pem TEXT NULL")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – parent_platforms (with extended columns)
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("ALTER TABLE parent_platforms ADD COLUMN IF NOT EXISTS catalog_batch_size INTEGER DEFAULT 0")
    _exec("ALTER TABLE parent_platforms ADD COLUMN IF NOT EXISTS catalog_push_delay_seconds INTEGER DEFAULT 0")
    _exec("ALTER TABLE parent_platforms ADD COLUMN IF NOT EXISTS transport VARCHAR(8) DEFAULT 'UDP'")
    _exec("ALTER TABLE parent_platforms ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) DEFAULT 'default'")
    _exec("ALTER TABLE parent_platforms ADD COLUMN IF NOT EXISTS last_keepalive TIMESTAMP")
    _exec("CREATE INDEX IF NOT EXISTS idx_parent_platforms_server_gb_id ON parent_platforms (server_gb_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_parent_platforms_enable ON parent_platforms (enable)")
    _exec("CREATE INDEX IF NOT EXISTS idx_parent_platforms_tenant_id ON parent_platforms (tenant_id)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – record_schedules
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_record_schedules_resource_id ON record_schedules (resource_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_record_schedules_plan_type ON record_schedules (plan_type)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – records (with extended columns)
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("ALTER TABLE records ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) DEFAULT 'default'")
    _exec("ALTER TABLE records ADD COLUMN IF NOT EXISTS record_app VARCHAR(32) NULL")
    _exec("ALTER TABLE records ADD COLUMN IF NOT EXISTS media_node_id VARCHAR(32) NULL")
    _exec("ALTER TABLE records ADD COLUMN IF NOT EXISTS zlm_file_path VARCHAR(512) NULL")
    _exec("ALTER TABLE records ADD COLUMN IF NOT EXISTS url_checked_at TIMESTAMP NULL")
    _exec("ALTER TABLE records ADD COLUMN IF NOT EXISTS url_ok BOOLEAN DEFAULT TRUE")
    _exec("ALTER TABLE records ADD COLUMN IF NOT EXISTS url_status_code INTEGER NULL")
    _exec("ALTER TABLE records ADD COLUMN IF NOT EXISTS url_error TEXT NULL")
    _exec("CREATE INDEX IF NOT EXISTS idx_records_asset_id ON records (asset_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_records_resource_id ON records (resource_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_records_start_time ON records (start_time)")
    _exec("CREATE INDEX IF NOT EXISTS idx_records_created_at ON records (created_at)")
    _exec("CREATE INDEX IF NOT EXISTS idx_records_tenant_id ON records (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_records_record_app ON records (record_app)")
    _exec("CREATE INDEX IF NOT EXISTS idx_records_media_node_id ON records (media_node_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_records_url_ok ON records (url_ok)")
    _exec("CREATE INDEX IF NOT EXISTS idx_records_url_checked_at ON records (url_checked_at)")
    _exec("CREATE INDEX IF NOT EXISTS idx_records_resource_start_time ON records (resource_id, start_time)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – record_schedule_runtimes
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_record_schedule_runtimes_tenant ON record_schedule_runtimes (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_record_schedule_runtimes_schedule ON record_schedule_runtimes (schedule_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_record_schedule_runtimes_resource ON record_schedule_runtimes (resource_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_record_schedule_runtimes_created_at ON record_schedule_runtimes (created_at)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – regions
    # ────────────────────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS regions (
            id VARCHAR(32) PRIMARY KEY,
            code VARCHAR(32) UNIQUE NOT NULL,
            name VARCHAR(128) NOT NULL,
            parent_id VARCHAR(32) NULL,
            level INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_regions_parent_id ON regions (parent_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_regions_code ON regions (code)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – asset_maintenances
    # ────────────────────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS asset_maintenances (
            id VARCHAR(32) PRIMARY KEY,
            asset_id VARCHAR(32) NOT NULL,
            maintenance_type VARCHAR(32) DEFAULT 'routine',
            maintenance_date TIMESTAMP NOT NULL,
            note TEXT NULL,
            operator VARCHAR(64) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_asset_maintenances_asset_id ON asset_maintenances (asset_id)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – organizations
    # ────────────────────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS organizations (
            id VARCHAR(32) PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            parent_id VARCHAR(32) NULL,
            tenant_id VARCHAR(64) DEFAULT 'default',
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_organizations_parent_id ON organizations (parent_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_organizations_tenant_id ON organizations (tenant_id)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – alarm_link_rules
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_alarm_link_rules_tenant_enabled ON alarm_link_rules (tenant_id, enabled)")
    _exec("CREATE INDEX IF NOT EXISTS idx_alarm_link_rules_org ON alarm_link_rules (organization_id)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – platform_catalog_resources
    # ────────────────────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS platform_catalog_resources (
            id VARCHAR(32) PRIMARY KEY,
            platform_id VARCHAR(32) NOT NULL,
            resource_id VARCHAR(32) NOT NULL,
            UNIQUE(platform_id, resource_id)
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_platform_catalog_resources_platform ON platform_catalog_resources (platform_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_platform_catalog_resources_resource ON platform_catalog_resources (resource_id)")
    _exec("ALTER TABLE platform_catalog_resources ADD COLUMN IF NOT EXISTS virtual_gb_id VARCHAR(64) NULL")
    _exec("ALTER TABLE platform_catalog_resources ADD COLUMN IF NOT EXISTS virtual_name VARCHAR(128) NULL")
    _exec("ALTER TABLE platform_catalog_resources ADD COLUMN IF NOT EXISTS virtual_parent_id VARCHAR(64) NULL")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – device_positions
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_device_positions_device_time ON device_positions (device_id, time)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – map_config
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("ALTER TABLE map_config ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) DEFAULT 'default'")
    _exec("ALTER TABLE map_config ADD COLUMN IF NOT EXISTS name VARCHAR(64) DEFAULT '默认地图'")
    _exec("ALTER TABLE map_config ADD COLUMN IF NOT EXISTS vector_tile_url VARCHAR(512) NULL")
    _exec("ALTER TABLE map_config ADD COLUMN IF NOT EXISTS min_zoom INTEGER DEFAULT 1")
    _exec("ALTER TABLE map_config ADD COLUMN IF NOT EXISTS max_zoom INTEGER DEFAULT 20")
    _exec("ALTER TABLE map_config ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE")
    _exec("CREATE INDEX IF NOT EXISTS idx_map_config_tenant ON map_config (tenant_id)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – network_metrics
    # ────────────────────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS network_metrics (
            id VARCHAR(32) PRIMARY KEY,
            tenant_id VARCHAR(64) DEFAULT 'default',
            metric VARCHAR(32) NOT NULL,
            value INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_network_metrics_metric_time ON network_metrics (metric, created_at)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – alarm_notifications
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_alarm_notifications_tenant_id ON alarm_notifications (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_alarm_notifications_sent_at ON alarm_notifications (sent_at)")
    _exec("CREATE INDEX IF NOT EXISTS idx_alarm_notifications_channel ON alarm_notifications (channel)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – app_logs
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_app_logs_tenant_id ON app_logs (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_app_logs_created_at ON app_logs (created_at)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – command_instructions
    # ────────────────────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS command_instructions (
            id VARCHAR(32) PRIMARY KEY,
            session_id VARCHAR(32) NOT NULL,
            content TEXT NOT NULL,
            user_id VARCHAR(32) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_command_instructions_session ON command_instructions (session_id)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – command_sessions
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_command_sessions_tenant ON command_sessions (tenant_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_command_sessions_status ON command_sessions (status)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – command_participants
    # ────────────────────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS command_participants (
            id VARCHAR(32) PRIMARY KEY,
            session_id VARCHAR(32) NOT NULL,
            user_id VARCHAR(32) NULL,
            username VARCHAR(64) NOT NULL,
            role VARCHAR(24) DEFAULT 'observer',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_command_participants_session ON command_participants (session_id)")

    # ────────────────────────────────────────────────────────────────
    # CREATE TABLE – structured_events
    # ────────────────────────────────────────────────────────────────
    _exec("""
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
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_structured_events_type_time ON structured_events (event_type, event_time)")


def downgrade() -> None:
    # ────────────────────────────────────────────────────────────────
    # Drop indexes (reverse order of creation)
    # ────────────────────────────────────────────────────────────────
    _exec("DROP INDEX IF EXISTS idx_structured_events_type_time")
    _exec("DROP INDEX IF EXISTS idx_command_participants_session")
    _exec("DROP INDEX IF EXISTS idx_command_sessions_status")
    _exec("DROP INDEX IF EXISTS idx_command_sessions_tenant")
    _exec("DROP INDEX IF EXISTS idx_command_instructions_session")
    _exec("DROP INDEX IF EXISTS idx_app_logs_created_at")
    _exec("DROP INDEX IF EXISTS idx_app_logs_tenant_id")
    _exec("DROP INDEX IF EXISTS idx_alarm_notifications_channel")
    _exec("DROP INDEX IF EXISTS idx_alarm_notifications_sent_at")
    _exec("DROP INDEX IF EXISTS idx_alarm_notifications_tenant_id")
    _exec("DROP INDEX IF EXISTS idx_network_metrics_metric_time")
    _exec("DROP INDEX IF EXISTS idx_map_config_tenant")
    _exec("DROP INDEX IF EXISTS idx_device_positions_device_time")
    _exec("DROP INDEX IF EXISTS idx_platform_catalog_resources_resource")
    _exec("DROP INDEX IF EXISTS idx_platform_catalog_resources_platform")
    _exec("DROP INDEX IF EXISTS idx_alarm_link_rules_org")
    _exec("DROP INDEX IF EXISTS idx_alarm_link_rules_tenant_enabled")
    _exec("DROP INDEX IF EXISTS idx_organizations_tenant_id")
    _exec("DROP INDEX IF EXISTS idx_organizations_parent_id")
    _exec("DROP INDEX IF EXISTS idx_asset_maintenances_asset_id")
    _exec("DROP INDEX IF EXISTS idx_regions_code")
    _exec("DROP INDEX IF EXISTS idx_regions_parent_id")
    _exec("DROP INDEX IF EXISTS idx_record_schedule_runtimes_created_at")
    _exec("DROP INDEX IF EXISTS idx_record_schedule_runtimes_resource")
    _exec("DROP INDEX IF EXISTS idx_record_schedule_runtimes_schedule")
    _exec("DROP INDEX IF EXISTS idx_record_schedule_runtimes_tenant")
    _exec("DROP INDEX IF EXISTS idx_records_resource_start_time")
    _exec("DROP INDEX IF EXISTS idx_records_url_checked_at")
    _exec("DROP INDEX IF EXISTS idx_records_url_ok")
    _exec("DROP INDEX IF EXISTS idx_records_media_node_id")
    _exec("DROP INDEX IF EXISTS idx_records_record_app")
    _exec("DROP INDEX IF EXISTS idx_records_tenant_id")
    _exec("DROP INDEX IF EXISTS idx_records_created_at")
    _exec("DROP INDEX IF EXISTS idx_records_start_time")
    _exec("DROP INDEX IF EXISTS idx_records_resource_id")
    _exec("DROP INDEX IF EXISTS idx_records_asset_id")
    _exec("DROP INDEX IF EXISTS idx_record_schedules_plan_type")
    _exec("DROP INDEX IF EXISTS idx_record_schedules_resource_id")
    _exec("DROP INDEX IF EXISTS idx_parent_platforms_tenant_id")
    _exec("DROP INDEX IF EXISTS idx_parent_platforms_enable")
    _exec("DROP INDEX IF EXISTS idx_parent_platforms_server_gb_id")
    _exec("DROP INDEX IF EXISTS idx_media_nodes_ip")
    _exec("DROP INDEX IF EXISTS idx_sip_trace_events_created_at")
    _exec("DROP INDEX IF EXISTS idx_sip_trace_events_channel_id")
    _exec("DROP INDEX IF EXISTS idx_sip_trace_events_device_id")
    _exec("DROP INDEX IF EXISTS idx_sip_trace_events_platform_id")
    _exec("DROP INDEX IF EXISTS idx_sip_trace_events_event")
    _exec("DROP INDEX IF EXISTS idx_sip_trace_events_trace_id")
    _exec("DROP INDEX IF EXISTS idx_sip_trace_events_tenant")
    _exec("DROP INDEX IF EXISTS idx_push_channels_gb_resource_id")
    _exec("DROP INDEX IF EXISTS idx_push_channels_key_prefix")
    _exec("DROP INDEX IF EXISTS idx_push_channels_stream_name")
    _exec("DROP INDEX IF EXISTS idx_push_channels_tenant")
    _exec("DROP INDEX IF EXISTS idx_access_sources_protocol")
    _exec("DROP INDEX IF EXISTS idx_access_sources_tenant")
    _exec("DROP INDEX IF EXISTS idx_operation_audits_created_at")
    _exec("DROP INDEX IF EXISTS idx_operation_audits_result")
    _exec("DROP INDEX IF EXISTS idx_operation_audits_operator")
    _exec("DROP INDEX IF EXISTS idx_operation_audits_module")
    _exec("DROP INDEX IF EXISTS idx_publish_records_publish_id")
    _exec("DROP INDEX IF EXISTS idx_config_drafts_updated_at")
    _exec("DROP INDEX IF EXISTS idx_config_drafts_draft_id")
    _exec("DROP INDEX IF EXISTS idx_config_revisions_revision")
    _exec("DROP INDEX IF EXISTS idx_platform_runtimes_platform_id")
    _exec("DROP INDEX IF EXISTS idx_platform_runtimes_tenant_id")
    _exec("DROP INDEX IF EXISTS idx_user_api_keys_prefix")
    _exec("DROP INDEX IF EXISTS idx_user_api_keys_user_id")
    _exec("DROP INDEX IF EXISTS idx_user_api_keys_tenant_id")
    _exec("DROP INDEX IF EXISTS idx_system_settings_key")
    _exec("DROP INDEX IF EXISTS idx_tenant_subscriptions_machine_code")
    _exec("DROP INDEX IF EXISTS idx_access_sources_gb_resource_id")
    _exec("DROP INDEX IF EXISTS idx_access_sources_gb_id")
    _exec("DROP INDEX IF EXISTS idx_access_sources_gb_enabled")
    _exec("DROP INDEX IF EXISTS idx_work_orders_category")
    _exec("DROP INDEX IF EXISTS idx_work_orders_status")
    _exec("DROP INDEX IF EXISTS idx_work_orders_tenant_id")
    _exec("DROP INDEX IF EXISTS idx_roles_code")
    _exec("DROP INDEX IF EXISTS idx_roles_tenant_id")
    _exec("DROP INDEX IF EXISTS idx_rtp_receive_tasks_status")
    _exec("DROP INDEX IF EXISTS idx_rtp_receive_tasks_stream_id")
    _exec("DROP INDEX IF EXISTS idx_rtp_receive_tasks_node_id")
    _exec("DROP INDEX IF EXISTS idx_rtp_receive_tasks_tenant_id")
    _exec("DROP INDEX IF EXISTS idx_ffmpeg_cmds_enabled")
    _exec("DROP INDEX IF EXISTS idx_ffmpeg_cmds_tenant_id")
    _exec("DROP INDEX IF EXISTS idx_platform_subscriptions_expires_at")
    _exec("DROP INDEX IF EXISTS idx_platform_subscriptions_event")
    _exec("DROP INDEX IF EXISTS idx_platform_subscriptions_platform_id")
    _exec("DROP INDEX IF EXISTS idx_platform_subscriptions_tenant_id")
    _exec("DROP INDEX IF EXISTS idx_device_subscriptions_asset_id")
    _exec("DROP INDEX IF EXISTS idx_device_subscriptions_tenant_id")
    _exec("DROP INDEX IF EXISTS idx_device_record_download_tasks_status")
    _exec("DROP INDEX IF EXISTS idx_device_record_download_tasks_call_id")
    _exec("DROP INDEX IF EXISTS idx_device_record_download_tasks_resource_id")
    _exec("DROP INDEX IF EXISTS idx_device_record_download_tasks_asset_id")
    _exec("DROP INDEX IF EXISTS idx_device_record_download_tasks_tenant_id")
    _exec("DROP INDEX IF EXISTS ix_stream_sessions_tenant_id")
    _exec("DROP INDEX IF EXISTS idx_stream_sessions_cascade_platform_id")
    _exec("DROP INDEX IF EXISTS idx_stream_sessions_media_server")
    _exec("DROP INDEX IF EXISTS idx_stream_sessions_ssrc")
    _exec("DROP INDEX IF EXISTS idx_stream_sessions_call_id")
    _exec("DROP INDEX IF EXISTS idx_media_port_leases_session")
    _exec("DROP INDEX IF EXISTS idx_media_port_leases_server")
    _exec("DROP INDEX IF EXISTS idx_alarms_tenant_time")
    _exec("DROP INDEX IF EXISTS idx_alarms_time")
    _exec("DROP INDEX IF EXISTS idx_alarms_tenant_id")
    _exec("DROP INDEX IF EXISTS ix_resources_numeric_channel_id")
    _exec("DROP INDEX IF EXISTS idx_resources_updated_at")
    _exec("DROP INDEX IF EXISTS idx_resources_created_at")
    _exec("DROP INDEX IF EXISTS idx_resources_status")
    _exec("DROP INDEX IF EXISTS idx_resources_asset_id")
    _exec("DROP INDEX IF EXISTS idx_resources_node_type")
    _exec("DROP INDEX IF EXISTS idx_resources_civil_code")
    _exec("DROP INDEX IF EXISTS idx_resources_region_parent_gb_id")
    _exec("DROP INDEX IF EXISTS idx_resources_parent_gb_id")
    _exec("DROP INDEX IF EXISTS idx_resources_tenant_id")
    _exec("DROP INDEX IF EXISTS idx_assets_updated_at")
    _exec("DROP INDEX IF EXISTS idx_assets_organization_id")
    _exec("DROP INDEX IF EXISTS idx_assets_tenant_id")
    _exec("DROP INDEX IF EXISTS idx_users_role")
    _exec("DROP INDEX IF EXISTS idx_users_tenant_id")

    # ────────────────────────────────────────────────────────────────
    # Drop tables (reverse order of creation)
    # ────────────────────────────────────────────────────────────────
    _exec("DROP TABLE IF EXISTS structured_events CASCADE")
    _exec("DROP TABLE IF EXISTS command_participants CASCADE")
    _exec("DROP TABLE IF EXISTS command_sessions CASCADE")
    _exec("DROP TABLE IF EXISTS command_instructions CASCADE")
    _exec("DROP TABLE IF EXISTS app_logs CASCADE")
    _exec("DROP TABLE IF EXISTS alarm_notifications CASCADE")
    _exec("DROP TABLE IF EXISTS network_metrics CASCADE")
    _exec("DROP TABLE IF EXISTS map_config CASCADE")
    _exec("DROP TABLE IF EXISTS device_positions CASCADE")
    _exec("DROP TABLE IF EXISTS platform_catalog_resources CASCADE")
    _exec("DROP TABLE IF EXISTS alarm_link_rules CASCADE")
    _exec("DROP TABLE IF EXISTS organizations CASCADE")
    _exec("DROP TABLE IF EXISTS asset_maintenances CASCADE")
    _exec("DROP TABLE IF EXISTS regions CASCADE")
    _exec("DROP TABLE IF EXISTS record_schedule_runtimes CASCADE")
    _exec("DROP TABLE IF EXISTS records CASCADE")
    _exec("DROP TABLE IF EXISTS record_schedules CASCADE")
    _exec("DROP TABLE IF EXISTS parent_platforms CASCADE")
    _exec("DROP TABLE IF EXISTS media_nodes CASCADE")
    _exec("DROP TABLE IF EXISTS sip_trace_events CASCADE")
    _exec("DROP TABLE IF EXISTS push_channels CASCADE")
    _exec("DROP TABLE IF EXISTS access_sources CASCADE")
    _exec("DROP TABLE IF EXISTS operation_audits CASCADE")
    _exec("DROP TABLE IF EXISTS publish_records CASCADE")
    _exec("DROP TABLE IF EXISTS config_drafts CASCADE")
    _exec("DROP TABLE IF EXISTS config_revisions CASCADE")
    _exec("DROP TABLE IF EXISTS platform_runtimes CASCADE")
    _exec("DROP TABLE IF EXISTS user_api_keys CASCADE")
    _exec("DROP TABLE IF EXISTS system_settings CASCADE")
    _exec("DROP TABLE IF EXISTS tenant_branding CASCADE")
    _exec("DROP TABLE IF EXISTS tenant_subscriptions CASCADE")
    _exec("DROP TABLE IF EXISTS billing_plans CASCADE")
    _exec("DROP TABLE IF EXISTS work_orders CASCADE")
    _exec("DROP TABLE IF EXISTS roles CASCADE")
    _exec("DROP TABLE IF EXISTS rtp_receive_tasks CASCADE")
    _exec("DROP TABLE IF EXISTS ffmpeg_cmds CASCADE")
    _exec("DROP TABLE IF EXISTS platform_subscriptions CASCADE")
    _exec("DROP TABLE IF EXISTS device_subscriptions CASCADE")
    _exec("DROP TABLE IF EXISTS device_record_download_tasks CASCADE")
    _exec("DROP TABLE IF EXISTS stream_sessions CASCADE")
    _exec("DROP TABLE IF EXISTS media_port_leases CASCADE")
