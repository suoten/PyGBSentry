"""catch-all schema migration for all models

Revision ID: e5f6a7b8c9d0
Revises: a1b2c3d4e5f6
Create Date: 2026-05-28 00:00:00.000000

This migration creates tables not covered by the previous migration
a1b2c3d4e5f6 using explicit op.create_table calls.

FIX [2026-07-12]: 原实现使用 op.create_table() 无存在性检查，而这 5 张表
（asset_stream_policies / asset_stream_health / device_clusters / cloud_clusters /
ip_blacklist）已由初始迁移 4bbb649f0063 创建。导致 alembic upgrade head 在
e5f6a7b8c9d0 处报 "table already exists" 中止，后续 9 个迁移（含字段补充
迁移）全部无法执行——这是"数据迁移缺字段"的根因。

修复：使用 sa.inspect() 检查表/索引是否存在后再创建（幂等），兼容
PostgreSQL / SQLite / MySQL。PostgreSQL 上 try/except 无法防止 DDL 错误
导致的事务 abort，必须用 inspect 预检。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    """检查表是否已存在（跨数据库兼容的幂等检查）。"""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    try:
        return inspector.has_table(table_name)
    except Exception:
        return False


def _index_exists(index_name: str, table_name: str) -> bool:
    """检查索引是否已存在。"""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    try:
        existing_indexes = [idx['name'] for idx in inspector.get_indexes(table_name)]
    except Exception:
        return False
    return index_name in existing_indexes


def upgrade() -> None:
    # asset_stream_policies
    if not _table_exists('asset_stream_policies'):
        op.create_table(
            'asset_stream_policies',
            sa.Column('id', sa.String(32), primary_key=True),
            sa.Column('asset_id', sa.String(32), sa.ForeignKey('assets.id'), unique=True, nullable=False),
            sa.Column('stream_mode', sa.String(32), nullable=False, server_default='GLOBAL'),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
        )
    if not _index_exists('ix_asset_stream_policies_asset_id', 'asset_stream_policies'):
        op.create_index('ix_asset_stream_policies_asset_id', 'asset_stream_policies', ['asset_id'])

    # asset_stream_health
    if not _table_exists('asset_stream_health'):
        op.create_table(
            'asset_stream_health',
            sa.Column('id', sa.String(32), primary_key=True),
            sa.Column('asset_id', sa.String(32), sa.ForeignKey('assets.id'), unique=True, nullable=False),
            sa.Column('last_mode', sa.String(32), nullable=False, server_default='UDP'),
            sa.Column('last_status_code', sa.Integer, nullable=False, server_default='0'),
            sa.Column('success_total', sa.Integer, nullable=False, server_default='0'),
            sa.Column('fail_total', sa.Integer, nullable=False, server_default='0'),
            sa.Column('consecutive_failures', sa.Integer, nullable=False, server_default='0'),
            sa.Column('auto_switch_count', sa.Integer, nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
        )
    if not _index_exists('ix_asset_stream_health_asset_id', 'asset_stream_health'):
        op.create_index('ix_asset_stream_health_asset_id', 'asset_stream_health', ['asset_id'])

    # device_clusters
    if not _table_exists('device_clusters'):
        op.create_table(
            'device_clusters',
            sa.Column('id', sa.String(32), primary_key=True),
            sa.Column('tenant_id', sa.String(64), server_default='default'),
            sa.Column('name', sa.String(128), nullable=False),
            sa.Column('description', sa.String(255), nullable=True),
            sa.Column('rules', sa.JSON, server_default='{}'),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
        )
    if not _index_exists('ix_device_clusters_tenant_id', 'device_clusters'):
        op.create_index('ix_device_clusters_tenant_id', 'device_clusters', ['tenant_id'])

    # cloud_clusters
    if not _table_exists('cloud_clusters'):
        op.create_table(
            'cloud_clusters',
            sa.Column('id', sa.String(32), primary_key=True),
            sa.Column('tenant_id', sa.String(64), server_default='default'),
            sa.Column('name', sa.String(128), nullable=False),
            sa.Column('region', sa.String(64), nullable=True),
            sa.Column('strategy', sa.String(64), server_default='latency'),
            sa.Column('node_ids', sa.JSON, server_default='[]'),
            sa.Column('meta', sa.JSON, server_default='{}'),
            sa.Column('enabled', sa.Boolean, server_default='1'),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
        )
    if not _index_exists('ix_cloud_clusters_tenant_id', 'cloud_clusters'):
        op.create_index('ix_cloud_clusters_tenant_id', 'cloud_clusters', ['tenant_id'])
    if not _index_exists('ix_cloud_clusters_enabled', 'cloud_clusters'):
        op.create_index('ix_cloud_clusters_enabled', 'cloud_clusters', ['enabled'])

    # ip_blacklist
    if not _table_exists('ip_blacklist'):
        op.create_table(
            'ip_blacklist',
            sa.Column('id', sa.String(32), primary_key=True),
            sa.Column('ip', sa.String(50), unique=True, nullable=False),
            sa.Column('reason', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        )
    if not _index_exists('ix_ip_blacklist_ip', 'ip_blacklist'):
        op.create_index('ix_ip_blacklist_ip', 'ip_blacklist', ['ip'])


def downgrade() -> None:
    op.drop_index('ix_ip_blacklist_ip', table_name='ip_blacklist')
    op.drop_table('ip_blacklist')

    op.drop_index('ix_cloud_clusters_enabled', table_name='cloud_clusters')
    op.drop_index('ix_cloud_clusters_tenant_id', table_name='cloud_clusters')
    op.drop_table('cloud_clusters')

    op.drop_index('ix_device_clusters_tenant_id', table_name='device_clusters')
    op.drop_table('device_clusters')

    op.drop_index('ix_asset_stream_health_asset_id', table_name='asset_stream_health')
    op.drop_table('asset_stream_health')

    op.drop_index('ix_asset_stream_policies_asset_id', table_name='asset_stream_policies')
    op.drop_table('asset_stream_policies')
