"""catch-all schema migration for all models

Revision ID: e5f6a7b8c9d0
Revises: a1b2c3d4e5f6
Create Date: 2026-05-28 00:00:00.000000

This migration creates tables not covered by the previous migration
a1b2c3d4e5f6 using explicit op.create_table calls.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'asset_stream_policies',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('asset_id', sa.String(32), sa.ForeignKey('assets.id'), unique=True, nullable=False),
        sa.Column('stream_mode', sa.String(32), nullable=False, server_default='GLOBAL'),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('ix_asset_stream_policies_asset_id', 'asset_stream_policies', ['asset_id'])

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
    op.create_index('ix_asset_stream_health_asset_id', 'asset_stream_health', ['asset_id'])

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
    op.create_index('ix_device_clusters_tenant_id', 'device_clusters', ['tenant_id'])

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
    op.create_index('ix_cloud_clusters_tenant_id', 'cloud_clusters', ['tenant_id'])
    op.create_index('ix_cloud_clusters_enabled', 'cloud_clusters', ['enabled'])

    op.create_table(
        'ip_blacklist',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('ip', sa.String(50), unique=True, nullable=False),
        sa.Column('reason', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
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
