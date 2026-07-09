"""add stream_id and app_name to media_port_leases

为 media_port_leases 表增加 stream_id 和 app_name 字段，
用于孤儿租约清理时正确关闭 ZLM RTP Server（closeRtpServer 需要 stream_id）。

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


def upgrade() -> None:
    op.add_column('media_port_leases', sa.Column('stream_id', sa.String(length=128), nullable=True))
    op.add_column('media_port_leases', sa.Column('app_name', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('media_port_leases', 'app_name')
    op.drop_column('media_port_leases', 'stream_id')
