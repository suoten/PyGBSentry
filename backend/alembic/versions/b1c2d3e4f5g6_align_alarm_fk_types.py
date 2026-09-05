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


def _find_alarm_device_fk_name() -> str | None:
    """查找 alarms.device_id 上的外键约束名（MySQL 自动命名为 alarms_ibfk_N）。

    FIX [2026-09-02 P1]: MySQL 不允许在仍被外键约束引用的列上直接 MODIFY 类型
    （错误 1832: Cannot change column 'device_id': used in a foreign key
    constraint 'alarms_ibfk_1'），必须先删除外键、改完类型再重建。
    PostgreSQL / SQLite（batch 重建表）不受影响，无需此步骤。
    """
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return None
    rows = bind.execute(sa.text(
        "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'alarms' "
        "AND COLUMN_NAME = 'device_id' AND REFERENCED_TABLE_NAME IS NOT NULL"
    )).fetchall()
    return str(rows[0][0]) if rows else None


def upgrade() -> None:
    # SQLite 不支持 ALTER COLUMN，需用 batch_alter_table
    # MySQL/PostgreSQL 直接 ALTER COLUMN ... TYPE
    fk_name = _find_alarm_device_fk_name()
    if fk_name:
        op.execute(f"ALTER TABLE alarms DROP FOREIGN KEY `{fk_name}`")
    try:
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
    finally:
        if fk_name:
            op.execute(
                f"ALTER TABLE alarms ADD CONSTRAINT `{fk_name}` "
                f"FOREIGN KEY (device_id) REFERENCES assets (gb_id)"
            )


def downgrade() -> None:
    fk_name = _find_alarm_device_fk_name()
    if fk_name:
        op.execute(f"ALTER TABLE alarms DROP FOREIGN KEY `{fk_name}`")
    try:
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
    finally:
        if fk_name:
            op.execute(
                f"ALTER TABLE alarms ADD CONSTRAINT `{fk_name}` "
                f"FOREIGN KEY (device_id) REFERENCES assets (gb_id)"
            )
