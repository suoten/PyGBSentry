"""add missing columns + indexes: comprehensive schema alignment

补充 ORM 模型已定义但无对应 Alembic 迁移的列和索引，并修复因 e5f6a7b8c9d0
重复建表 bug 导致的迁移链中断问题。

== 背景 ==
e5f6a7b8c9d0 (catch-all) 使用 op.create_table() 无存在性检查，而其创建的 5 张
表已由初始迁移 4bbb649f0063 创建。导致 alembic upgrade head 在 e5f6a7b8c9d0 处
报 "table already exists" 中止。启动代码随后执行 stamp head，将 alembic_version
标记为 k3c4d5e6f7g8（旧 head），但 f1a2b3c4d5e6 ~ k3c4d5e6f7g8 这 5 个迁移实际
从未执行——它们添加的列在受影响的数据库上全部缺失。

== 本迁移修复的内容 ==
1. 新增遗漏列（所有数据库都需要）：
   - config_drafts.created_at (DateTime)
   - ip_blacklist.tenant_id (String(64), default='default', index=True)
   - ip_blacklist.ip 类型从 VARCHAR(50) 扩宽到 VARCHAR(64)

2. 补齐被跳过迁移的列（仅受 stamp head bug 影响的数据库需要，幂等）：
   - f1a2b3c4d5e6: users.auth_provider, official_user_id, official_tenant_id,
     official_username, official_access_token, official_token_expires_at
   - g1a2b3c4d5e6: media_port_leases.stream_id, app_name
   - i1a2b3c4d5e6: tenant_subscriptions.downgrade_history, alarms.longitude/latitude
   - j2b3c4d5e6f7: operation_audits.tenant_id
   - k3c4d5e6f7g8: users.auth_domain, site_role, agreed_tos_version,
     agreed_privacy_version, agreed_dev_version

3. 补齐初始迁移 4bbb649f0063 遗漏的列（所有数据库都需要）：
   初始迁移从旧版 ORM 模型自动生成，遗漏了后续添加到 ORM 的列。
   a1b2c3d4e5f6 尝试用 "ADD COLUMN IF NOT EXISTS" 补救，但该语法
   SQLite 不支持（错误被 _exec 静默吞掉），PostgreSQL 上正常。
   - billing_plans: price_yearly, description, sort_order
   - stream_sessions: tenant_id, cascade_call_id, cascade_from_tag, cascade_to_tag

4. 补齐初始迁移和 a1b2c3d4e5f6 遗漏/命名不匹配的索引（所有数据库都需要）：
   a1b2c3d4e5f6 创建了 idx_* 前缀的索引，但 ORM 期望 ix_* 前缀。
   部分索引在初始迁移和 a1b2c3d4e5f6 中均完全遗漏。
   - assets, config_drafts, media_nodes, operation_audits, parent_platforms,
     records, resources, stream_sessions 上的 20 个索引

采用 sa.inspect() 预检（幂等），兼容 PostgreSQL / SQLite / MySQL。
PostgreSQL 上 try/except 无法防止 DDL 错误导致的事务 abort。

Revision ID: l4e5f6a7b8c9d
Revises: k3c4d5e6f7g8
Create Date: 2026-07-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'l4e5f6a7b8c9d'
down_revision: Union[str, None] = 'k3c4d5e6f7g8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    """检查列是否已存在（跨数据库兼容的幂等检查）。

    使用 sa.inspect() 检查列是否存在，避免 PostgreSQL 的
    InFailedSQLTransactionError（try/except 无法防止 PostgreSQL
    事务 abort）。
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    try:
        existing_columns = [c['name'] for c in inspector.get_columns(table_name)]
    except Exception:
        return False
    return column_name in existing_columns


def _index_exists(index_name: str, table_name: str) -> bool:
    """检查索引是否已存在。"""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    try:
        existing_indexes = [idx['name'] for idx in inspector.get_indexes(table_name)]
    except Exception:
        return False
    return index_name in existing_indexes


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    """幂等添加列。"""
    if not _column_exists(table_name, column.name):
        op.add_column(table_name, column)


def _create_index_if_missing(index_name: str, table_name: str, columns: list, unique: bool = False) -> None:
    """幂等创建索引。"""
    if not _index_exists(index_name, table_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    # ────────────────────────────────────────────────────────────────
    # 1. 新增遗漏列（所有数据库都需要）
    # ────────────────────────────────────────────────────────────────
    _add_column_if_missing('config_drafts', sa.Column('created_at', sa.DateTime(), nullable=True))

    _add_column_if_missing('ip_blacklist', sa.Column('tenant_id', sa.String(length=64), nullable=True, server_default='default'))
    _create_index_if_missing('ix_ip_blacklist_tenant_id', 'ip_blacklist', ['tenant_id'])

    # ip_blacklist.ip: VARCHAR(50) -> VARCHAR(64)，与 ORM 模型对齐
    bind = op.get_bind()
    dialect = (getattr(getattr(bind, 'dialect', None), 'name', '') or '').lower()
    if dialect.startswith('post'):
        op.execute("ALTER TABLE ip_blacklist ALTER COLUMN ip TYPE VARCHAR(64)")
    elif dialect == 'mysql':
        op.execute("ALTER TABLE ip_blacklist MODIFY COLUMN ip VARCHAR(64) NOT NULL")
    # SQLite: VARCHAR 长度不强制约束，跳过

    # ────────────────────────────────────────────────────────────────
    # 2. 补齐被跳过迁移的列（仅受 stamp head bug 影响的数据库需要，幂等）
    # ────────────────────────────────────────────────────────────────

    # --- f1a2b3c4d5e6: users SSO 字段 ---
    _add_column_if_missing('users', sa.Column('auth_provider', sa.String(length=32), nullable=False, server_default='local'))
    _add_column_if_missing('users', sa.Column('official_user_id', sa.String(length=64), nullable=True))
    _add_column_if_missing('users', sa.Column('official_tenant_id', sa.String(length=64), nullable=True))
    _add_column_if_missing('users', sa.Column('official_username', sa.String(length=64), nullable=True))
    _add_column_if_missing('users', sa.Column('official_access_token', sa.Text(), nullable=True))
    _add_column_if_missing('users', sa.Column('official_token_expires_at', sa.DateTime(), nullable=True))
    _create_index_if_missing('ix_users_official_user_id', 'users', ['official_user_id'], unique=True)

    # --- g1a2b3c4d5e6: media_port_leases.stream_id, app_name ---
    _add_column_if_missing('media_port_leases', sa.Column('stream_id', sa.String(length=128), nullable=True))
    _add_column_if_missing('media_port_leases', sa.Column('app_name', sa.String(length=64), nullable=True))

    # --- i1a2b3c4d5e6: tenant_subscriptions.downgrade_history, alarms.longitude/latitude ---
    _add_column_if_missing('tenant_subscriptions', sa.Column('downgrade_history', sa.JSON(), nullable=True))
    _add_column_if_missing('alarms', sa.Column('longitude', sa.Float(), nullable=True))
    _add_column_if_missing('alarms', sa.Column('latitude', sa.Float(), nullable=True))

    # --- j2b3c4d5e6f7: operation_audits.tenant_id ---
    _add_column_if_missing('operation_audits', sa.Column('tenant_id', sa.String(length=36), nullable=True))

    # --- k3c4d5e6f7g8: users.auth_domain, site_role, agreed_*_version ---
    _add_column_if_missing('users', sa.Column('auth_domain', sa.String(length=16), nullable=True, server_default='tenant'))
    _create_index_if_missing('ix_users_auth_domain', 'users', ['auth_domain'])
    _add_column_if_missing('users', sa.Column('site_role', sa.String(length=32), nullable=True, server_default='normal'))
    _create_index_if_missing('ix_users_site_role', 'users', ['site_role'])
    _add_column_if_missing('users', sa.Column('agreed_tos_version', sa.String(length=32), nullable=True))
    _add_column_if_missing('users', sa.Column('agreed_privacy_version', sa.String(length=32), nullable=True))
    _add_column_if_missing('users', sa.Column('agreed_dev_version', sa.String(length=32), nullable=True))

    # ────────────────────────────────────────────────────────────────
    # 3. 补齐初始迁移 4bbb649f0063 遗漏的列（所有数据库都需要）
    # 初始迁移从旧版 ORM 自动生成，遗漏了后续添加的列。
    # a1b2c3d4e5f6 用 "ADD COLUMN IF NOT EXISTS" 补救，但 SQLite 不支持
    # 该语法（错误被 _exec 静默吞掉），PostgreSQL 上正常。
    # ────────────────────────────────────────────────────────────────

    # --- billing_plans: price_yearly, description, sort_order ---
    _add_column_if_missing('billing_plans', sa.Column('price_yearly', sa.Integer(), nullable=True))
    _add_column_if_missing('billing_plans', sa.Column('description', sa.Text(), nullable=True))
    _add_column_if_missing('billing_plans', sa.Column('sort_order', sa.Integer(), nullable=True, server_default='0'))

    # --- stream_sessions: tenant_id, cascade_call_id, cascade_from_tag, cascade_to_tag ---
    _add_column_if_missing('stream_sessions', sa.Column('tenant_id', sa.String(length=64), nullable=True, server_default='default'))
    _add_column_if_missing('stream_sessions', sa.Column('cascade_call_id', sa.String(length=128), nullable=True))
    _add_column_if_missing('stream_sessions', sa.Column('cascade_from_tag', sa.String(length=64), nullable=True))
    _add_column_if_missing('stream_sessions', sa.Column('cascade_to_tag', sa.String(length=64), nullable=True))

    # ────────────────────────────────────────────────────────────────
    # 4. 补齐遗漏/命名不匹配的索引（所有数据库都需要）
    # a1b2c3d4e5f6 创建了 idx_* 前缀索引，ORM 期望 ix_* 前缀。
    # 部分索引在初始迁移和 a1b2c3d4e5f6 中均完全遗漏。
    # ────────────────────────────────────────────────────────────────

    # --- assets ---
    _create_index_if_missing('ix_assets_updated_at', 'assets', ['updated_at'])

    # --- config_drafts ---
    _create_index_if_missing('ix_config_drafts_updated_at', 'config_drafts', ['updated_at'])

    # --- media_nodes ---
    _create_index_if_missing('ix_media_nodes_ip', 'media_nodes', ['ip'])

    # --- operation_audits ---
    _create_index_if_missing('ix_operation_audits_action', 'operation_audits', ['action'])
    _create_index_if_missing('ix_operation_audits_created_at', 'operation_audits', ['created_at'])
    _create_index_if_missing('ix_operation_audits_operator', 'operation_audits', ['operator'])
    _create_index_if_missing('ix_operation_audits_result', 'operation_audits', ['result'])

    # --- parent_platforms ---
    _create_index_if_missing('ix_parent_platforms_enable', 'parent_platforms', ['enable'])
    _create_index_if_missing('ix_parent_platforms_server_gb_id', 'parent_platforms', ['server_gb_id'], unique=True)

    # --- records ---
    _create_index_if_missing('ix_records_end_time', 'records', ['end_time'])
    _create_index_if_missing('ix_records_stream_id', 'records', ['stream_id'])
    _create_index_if_missing('ix_records_tenant_start_time', 'records', ['tenant_id', 'start_time'])
    _create_index_if_missing('ix_records_resource_start_end', 'records', ['resource_id', 'start_time', 'end_time'])

    # --- resources ---
    _create_index_if_missing('ix_resources_created_at', 'resources', ['created_at'])
    _create_index_if_missing('ix_resources_status', 'resources', ['status'])
    _create_index_if_missing('ix_resources_updated_at', 'resources', ['updated_at'])

    # --- stream_sessions ---
    _create_index_if_missing('ix_stream_sessions_asset_id', 'stream_sessions', ['asset_id'])
    _create_index_if_missing('ix_stream_sessions_media_server_id', 'stream_sessions', ['media_server_id'])
    _create_index_if_missing('ix_stream_sessions_resource_id', 'stream_sessions', ['resource_id'])
    _create_index_if_missing('ix_stream_sessions_tenant_id', 'stream_sessions', ['tenant_id'])


def _drop_index_safely(index_name: str, table_name: str) -> None:
    """幂等删除索引。"""
    if _index_exists(index_name, table_name):
        op.drop_index(index_name, table_name=table_name)


def _drop_column_safely(table_name: str, column_name: str) -> None:
    """幂等删除列。"""
    if _column_exists(table_name, column_name):
        op.drop_column(table_name, column_name)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = (getattr(getattr(bind, 'dialect', None), 'name', '') or '').lower()
    if dialect.startswith('post'):
        op.execute("ALTER TABLE ip_blacklist ALTER COLUMN ip TYPE VARCHAR(50)")
    elif dialect == 'mysql':
        op.execute("ALTER TABLE ip_blacklist MODIFY COLUMN ip VARCHAR(50) NOT NULL")

    # --- 4. 回滚新增索引 ---
    for idx_name, tbl in [
        ('ix_stream_sessions_tenant_id', 'stream_sessions'),
        ('ix_stream_sessions_resource_id', 'stream_sessions'),
        ('ix_stream_sessions_media_server_id', 'stream_sessions'),
        ('ix_stream_sessions_asset_id', 'stream_sessions'),
        ('ix_resources_updated_at', 'resources'),
        ('ix_resources_status', 'resources'),
        ('ix_resources_created_at', 'resources'),
        ('ix_records_resource_start_end', 'records'),
        ('ix_records_tenant_start_time', 'records'),
        ('ix_records_stream_id', 'records'),
        ('ix_records_end_time', 'records'),
        ('ix_parent_platforms_server_gb_id', 'parent_platforms'),
        ('ix_parent_platforms_enable', 'parent_platforms'),
        ('ix_operation_audits_result', 'operation_audits'),
        ('ix_operation_audits_operator', 'operation_audits'),
        ('ix_operation_audits_created_at', 'operation_audits'),
        ('ix_operation_audits_action', 'operation_audits'),
        ('ix_media_nodes_ip', 'media_nodes'),
        ('ix_config_drafts_updated_at', 'config_drafts'),
        ('ix_assets_updated_at', 'assets'),
    ]:
        _drop_index_safely(idx_name, tbl)

    # --- 3. 回滚新增列 ---
    for col, tbl in [
        ('cascade_to_tag', 'stream_sessions'),
        ('cascade_from_tag', 'stream_sessions'),
        ('cascade_call_id', 'stream_sessions'),
        ('tenant_id', 'stream_sessions'),
        ('sort_order', 'billing_plans'),
        ('description', 'billing_plans'),
        ('price_yearly', 'billing_plans'),
    ]:
        _drop_column_safely(tbl, col)

    # --- 2. 回滚被跳过迁移的列 ---
    for col, tbl in [
        ('agreed_dev_version', 'users'),
        ('agreed_privacy_version', 'users'),
        ('agreed_tos_version', 'users'),
        ('site_role', 'users'),
        ('auth_domain', 'users'),
        ('tenant_id', 'operation_audits'),
        ('latitude', 'alarms'),
        ('longitude', 'alarms'),
        ('downgrade_history', 'tenant_subscriptions'),
        ('app_name', 'media_port_leases'),
        ('stream_id', 'media_port_leases'),
        ('official_token_expires_at', 'users'),
        ('official_access_token', 'users'),
        ('official_username', 'users'),
        ('official_tenant_id', 'users'),
        ('official_user_id', 'users'),
        ('auth_provider', 'users'),
    ]:
        _drop_column_safely(tbl, col)
    _drop_index_safely('ix_users_site_role', 'users')
    _drop_index_safely('ix_users_auth_domain', 'users')
    _drop_index_safely('ix_users_official_user_id', 'users')

    # --- 1. 回滚新增遗漏列 ---
    _drop_index_safely('ix_ip_blacklist_tenant_id', 'ip_blacklist')
    _drop_column_safely('ip_blacklist', 'tenant_id')
    _drop_column_safely('config_drafts', 'created_at')
