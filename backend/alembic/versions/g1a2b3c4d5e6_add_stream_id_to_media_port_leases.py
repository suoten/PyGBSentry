"""add stream_id and app_name to media_port_leases

为 media_port_leases 表增加 stream_id 和 app_name 字段，
用于孤儿租约清理时正确关闭 ZLM RTP Server（closeRtpServer 需要 stream_id）。

FIX [2026-07-12]: 原实现使用 op.add_column() 无存在性检查，在 PostgreSQL 上
若列已存在（如 create_all 兜底建表后）会报 DuplicateColumn 错误并导致事务
abort。改为 sa.inspect() 预检。

Revision ID: g1a2b3c4d5e6
Revises: f1a2b3c4d5e6
Create Date: 2026-07-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'g1a2b3c4d5e6'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    """检查列是否已存在（跨数据库兼容的幂等检查）。"""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    try:
        existing_columns = [c['name'] for c in inspector.get_columns(table_name)]
    except Exception:
        return False
    return column_name in existing_columns


def upgrade() -> None:
    if not _column_exists('media_port_leases', 'stream_id'):
        op.add_column('media_port_leases', sa.Column('stream_id', sa.String(length=128), nullable=True))
    if not _column_exists('media_port_leases', 'app_name'):
        op.add_column('media_port_leases', sa.Column('app_name', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('media_port_leases', 'app_name')
    op.drop_column('media_port_leases', 'stream_id')
