"""add official account (SSO) fields to users

为开源版「官网账户登录」(SSO) 增加 users 表绑定字段：
- auth_provider / official_user_id / official_tenant_id / official_username
- official_access_token / official_token_expires_at （缓存官网 token）

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


def upgrade() -> None:
    op.add_column('users', sa.Column('auth_provider', sa.String(length=32), nullable=False, server_default='local'))
    op.add_column('users', sa.Column('official_user_id', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('official_tenant_id', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('official_username', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('official_access_token', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('official_token_expires_at', sa.DateTime(), nullable=True))
    op.create_index('ix_users_official_user_id', 'users', ['official_user_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_users_official_user_id', table_name='users')
    op.drop_column('users', 'official_token_expires_at')
    op.drop_column('users', 'official_access_token')
    op.drop_column('users', 'official_username')
    op.drop_column('users', 'official_tenant_id')
    op.drop_column('users', 'official_user_id')
    op.drop_column('users', 'auth_provider')
