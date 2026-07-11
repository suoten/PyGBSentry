"""add missing user columns: auth_domain, site_role, agreed_*_version

补充 users 表 ORM 模型已定义但缺失 alembic 迁移的 5 个列：
- auth_domain (String(16), default='tenant') — 认证域（local/tenant/sso）
- site_role (String(32), default='normal') — 站点角色
- agreed_tos_version (String(32)) — 已同意服务条款版本
- agreed_privacy_version (String(32)) — 已同意隐私政策版本
- agreed_dev_version (String(32)) — 已同意开发者协议版本

根因：User 模型（app/models/user.py）已定义这些列，但初始迁移
4bbb649f0063 创建 users 表时未包含，且后续无迁移补充。
当数据库通过 alembic 迁移建表时（而非 create_all），这些列缺失，
导致 init_db 查询 User 时 ProgrammingError: column does not exist。

本迁移采用 sa.inspect() 检查列是否存在后再添加（幂等），
避免 PostgreSQL 事务中止问题（try/except 在 PostgreSQL 上无法
防止 DDL 错误导致的事务 abort）。

Revision ID: k3c4d5e6f7g8
Revises: j2b3c4d5e6f7
Create Date: 2026-07-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k3c4d5e6f7g8'
down_revision: Union[str, Sequence[str], None] = 'j2b3c4d5e6f7'
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
    # auth_domain
    if not _column_exists('users', 'auth_domain'):
        op.add_column('users', sa.Column('auth_domain', sa.String(length=16), nullable=True, server_default='tenant'))
    if not _index_exists('ix_users_auth_domain', 'users'):
        op.create_index('ix_users_auth_domain', 'users', ['auth_domain'], unique=False)

    # site_role
    if not _column_exists('users', 'site_role'):
        op.add_column('users', sa.Column('site_role', sa.String(length=32), nullable=True, server_default='normal'))
    if not _index_exists('ix_users_site_role', 'users'):
        op.create_index('ix_users_site_role', 'users', ['site_role'], unique=False)

    # agreed_tos_version
    if not _column_exists('users', 'agreed_tos_version'):
        op.add_column('users', sa.Column('agreed_tos_version', sa.String(length=32), nullable=True))

    # agreed_privacy_version
    if not _column_exists('users', 'agreed_privacy_version'):
        op.add_column('users', sa.Column('agreed_privacy_version', sa.String(length=32), nullable=True))

    # agreed_dev_version
    if not _column_exists('users', 'agreed_dev_version'):
        op.add_column('users', sa.Column('agreed_dev_version', sa.String(length=32), nullable=True))


def downgrade() -> None:
    try:
        op.drop_column('users', 'agreed_dev_version')
    except Exception:
        pass
    try:
        op.drop_column('users', 'agreed_privacy_version')
    except Exception:
        pass
    try:
        op.drop_column('users', 'agreed_tos_version')
    except Exception:
        pass
    try:
        op.drop_index('ix_users_site_role', table_name='users')
    except Exception:
        pass
    try:
        op.drop_column('users', 'site_role')
    except Exception:
        pass
    try:
        op.drop_index('ix_users_auth_domain', table_name='users')
    except Exception:
        pass
    try:
        op.drop_column('users', 'auth_domain')
    except Exception:
        pass
