"""add official account (SSO) fields to users

为开源版「官网账户登录」(SSO) 增加 users 表绑定字段：
- auth_provider / official_user_id / official_tenant_id / official_username
- official_access_token / official_token_expires_at （缓存官网 token）

FIX [2026-07-12]: 原实现使用 op.add_column() 无存在性检查，在 PostgreSQL 上
若列已存在（如 create_all 兜底建表后）会报 DuplicateColumn 错误并导致事务
abort，使整个迁移链中断。改为 sa.inspect() 预检（PostgreSQL 上 try/except
无法防止 DDL 错误导致的事务 abort）。

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-06-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
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
    if not _column_exists('users', 'auth_provider'):
        op.add_column('users', sa.Column('auth_provider', sa.String(length=32), nullable=False, server_default='local'))
    if not _column_exists('users', 'official_user_id'):
        op.add_column('users', sa.Column('official_user_id', sa.String(length=64), nullable=True))
    if not _column_exists('users', 'official_tenant_id'):
        op.add_column('users', sa.Column('official_tenant_id', sa.String(length=64), nullable=True))
    if not _column_exists('users', 'official_username'):
        op.add_column('users', sa.Column('official_username', sa.String(length=64), nullable=True))
    if not _column_exists('users', 'official_access_token'):
        op.add_column('users', sa.Column('official_access_token', sa.Text(), nullable=True))
    if not _column_exists('users', 'official_token_expires_at'):
        op.add_column('users', sa.Column('official_token_expires_at', sa.DateTime(), nullable=True))
    if not _index_exists('ix_users_official_user_id', 'users'):
        op.create_index('ix_users_official_user_id', 'users', ['official_user_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_users_official_user_id', table_name='users')
    op.drop_column('users', 'official_token_expires_at')
    op.drop_column('users', 'official_access_token')
    op.drop_column('users', 'official_username')
    op.drop_column('users', 'official_tenant_id')
    op.drop_column('users', 'official_user_id')
    op.drop_column('users', 'auth_provider')
