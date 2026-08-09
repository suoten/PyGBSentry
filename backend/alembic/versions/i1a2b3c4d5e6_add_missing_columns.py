"""add missing columns: tenant_subscriptions.downgrade_history, alarms.longitude/latitude

补充缺失的数据库列，使模型定义与实际 schema 对齐：
- tenant_subscriptions.downgrade_history (JSON) — 降级历史记录
- alarms.longitude (Float) — 报警经度
- alarms.latitude (Float) — 报警纬度

根因：模型已定义这些列但无对应 Alembic 迁移，旧库（SQLite/PostgreSQL）
通过 create_all 建表时缺少这些列，导致查询时 OperationalError。

FIX [2026-07-12]: 原实现使用 try/except 包裹 op.add_column，在 PostgreSQL 上
无法防止 DDL 错误导致的事务 abort（PostgreSQL 的 DDL 错误会将整个事务标记
为 aborted，后续所有语句都会报 InFailedSQLTransactionError）。改为
sa.inspect() 预检列是否存在后再添加。

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
        # 表不存在时返回 False（create_all 会创建完整表）
        return False
    return column_name in existing_columns


def upgrade() -> None:
    # FIX: [2026-07-04] 补充 tenant_subscriptions.downgrade_history 列 [全栈工程师]
    # FIX: [2026-07-12] 改为 inspect 预检，兼容 PostgreSQL [数据库工程师]
    if not _column_exists('tenant_subscriptions', 'downgrade_history'):
        op.add_column('tenant_subscriptions', sa.Column('downgrade_history', sa.JSON(), nullable=True))

    # FIX: [2026-07-04] 补充 alarms.longitude/latitude 列 [全栈工程师]
    if not _column_exists('alarms', 'longitude'):
        op.add_column('alarms', sa.Column('longitude', sa.Float(), nullable=True))
    if not _column_exists('alarms', 'latitude'):
        op.add_column('alarms', sa.Column('latitude', sa.Float(), nullable=True))


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
