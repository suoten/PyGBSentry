"""align alarm fk types

Revision ID: b1c2d3e4f5g6
Revises: f1a2b3c4d5e6
Create Date: 2026-06-28

P0-11#2: 修复 alarms.device_id / channel_id 外键类型不一致
- alarms.device_id 从 String(32) 改为 String(20)，与 assets.gb_id 对齐
- alarms.channel_id 从 String(32) 改为 String(20)，与 GB28181 国标编码长度对齐
- 防止 MySQL strict mode / PostgreSQL 上的 FK 约束失败
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5g6'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite 不支持 ALTER COLUMN，需用 batch_alter_table
    # MySQL/PostgreSQL 直接 ALTER COLUMN ... TYPE
    with op.batch_alter_table('alarms', schema=None) as batch_op:
        batch_op.alter_column(
            'device_id',
            existing_type=sa.String(32),
            type_=sa.String(20),
            existing_nullable=False,
            existing_server_default=None,
        )
        batch_op.alter_column(
            'channel_id',
            existing_type=sa.String(32),
            type_=sa.String(20),
            existing_nullable=True,
            existing_server_default=None,
        )


def downgrade() -> None:
    with op.batch_alter_table('alarms', schema=None) as batch_op:
        batch_op.alter_column(
            'channel_id',
            existing_type=sa.String(20),
            type_=sa.String(32),
            existing_nullable=True,
            existing_server_default=None,
        )
        batch_op.alter_column(
            'device_id',
            existing_type=sa.String(20),
            type_=sa.String(32),
            existing_nullable=False,
            existing_server_default=None,
        )
