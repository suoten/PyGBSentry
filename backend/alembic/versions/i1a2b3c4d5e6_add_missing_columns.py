"""add missing columns: tenant_subscriptions.downgrade_history, alarms.longitude/latitude

补充缺失的数据库列，使模型定义与实际 schema 对齐：
- tenant_subscriptions.downgrade_history (JSON) — 降级历史记录
- alarms.longitude (Float) — 报警经度
- alarms.latitude (Float) — 报警纬度

根因：模型已定义这些列但无对应 Alembic 迁移，旧库（SQLite/PostgreSQL）
通过 create_all 建表时缺少这些列，导致查询时 OperationalError。

Revision ID: i1a2b3c4d5e6
Revises: h1a2b3c4d5e6
Create Date: 2026-07-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'h1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # FIX: [2026-07-04] 补充 tenant_subscriptions.downgrade_history 列 [全栈工程师]
    try:
        op.add_column('tenant_subscriptions', sa.Column('downgrade_history', sa.JSON(), nullable=True))
    except Exception:
        pass  # 列已存在时忽略

    # FIX: [2026-07-04] 补充 alarms.longitude/latitude 列 [全栈工程师]
    try:
        op.add_column('alarms', sa.Column('longitude', sa.Float(), nullable=True))
    except Exception:
        pass
    try:
        op.add_column('alarms', sa.Column('latitude', sa.Float(), nullable=True))
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_column('alarms', 'latitude')
    except Exception:
        pass
    try:
        op.drop_column('alarms', 'longitude')
    except Exception:
        pass
    try:
        op.drop_column('tenant_subscriptions', 'downgrade_history')
    except Exception:
        pass
