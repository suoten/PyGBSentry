"""add operation_audits.tenant_id column

补充 operation_audits.tenant_id 列，使数据库 schema 与 ORM 模型对齐。

根因：OperationAudit 模型（app/models/operation_audit.py:34）已定义
``tenant_id = Column(String(36), nullable=True)`` 用于多租户审计隔离，
但初始迁移（4bbb649f0063）和业务扩展迁移（a1b2c3d4e5f6）创建
operation_audits 表时均未包含此列。audit_center_service 写入审计
日志时会尝试设置 tenant_id，在仅有 Alembic 建表路径的旧库上触发
OperationalError: no such column: tenant_id，导致审计日志写入失败。

FIX [2026-07-12]: 原实现使用 try/except 包裹 op.add_column，在 PostgreSQL 上
无法防止 DDL 错误导致的事务 abort。改为 sa.inspect() 预检列是否存在后再添加。

Revision ID: j2b3c4d5e6f7
Revises: i1a2b3c4d5e6
Create Date: 2026-07-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'i1a2b3c4d5e6'
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


def upgrade() -> None:
    # FIX: [2026-07-04] 补充 operation_audits.tenant_id 列，对齐 ORM 模型定义 [全栈工程师]
    # FIX: [2026-07-12] 改为 inspect 预检，兼容 PostgreSQL [数据库工程师]
    if not _column_exists('operation_audits', 'tenant_id'):
        op.add_column('operation_audits', sa.Column('tenant_id', sa.String(length=36), nullable=True))


def downgrade() -> None:
    try:
        op.drop_column('operation_audits', 'tenant_id')
    except Exception:
        pass
