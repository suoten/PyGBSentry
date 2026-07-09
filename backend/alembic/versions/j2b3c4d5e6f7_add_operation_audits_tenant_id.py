"""add operation_audits.tenant_id column

补充 operation_audits.tenant_id 列，使数据库 schema 与 ORM 模型对齐。

根因：OperationAudit 模型（app/models/operation_audit.py:34）已定义
``tenant_id = Column(String(36), nullable=True)`` 用于多租户审计隔离，
但初始迁移（4bbb649f0063）和业务扩展迁移（a1b2c3d4e5f6）创建
operation_audits 表时均未包含此列。audit_center_service 写入审计
日志时会尝试设置 tenant_id，在仅有 Alembic 建表路径的旧库上触发
OperationalError: no such column: tenant_id，导致审计日志写入失败。

本迁移在最新 head（i1a2b3c4d5e6）之上补齐该列，采用幂等 try/except
模式以兼容已通过 create_all 建好该列的库。

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


def upgrade() -> None:
    # FIX: [2026-07-04] 补充 operation_audits.tenant_id 列，对齐 ORM 模型定义 [全栈工程师]
    # 根因：模型已定义 tenant_id 但 Alembic 建表迁移遗漏该列，导致 audit_center_service
    # 写入审计日志时 OperationalError。采用幂等模式避免重复列错误。
    try:
        op.add_column('operation_audits', sa.Column('tenant_id', sa.String(length=36), nullable=True))
    except Exception:
        pass  # 列已存在时忽略（create_all 路径已建好该列的库）


def downgrade() -> None:
    try:
        op.drop_column('operation_audits', 'tenant_id')
    except Exception:
        pass
