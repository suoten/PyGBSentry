"""widen records.file_path from 255 to 512

F-DB-002: 模型 Record.file_path 已改为 String(512)（与 zlm_file_path 一致），
但历史迁移建表时为 255，长路径（含 query 参数/签名 token）会被截断导致播放/下载失败。
本迁移仅在 PostgreSQL/MySQL 上执行 ALTER COLUMN TYPE，SQLite 不强制 VARCHAR 长度无需迁移。

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name.lower()
    if dialect.startswith("post"):
        op.execute("ALTER TABLE records ALTER COLUMN file_path TYPE VARCHAR(512)")
    elif dialect == "mysql":
        op.execute("ALTER TABLE records MODIFY COLUMN file_path VARCHAR(512) NOT NULL")
    # SQLite: VARCHAR 长度不强制约束，无需迁移


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name.lower()
    if dialect.startswith("post"):
        op.execute("ALTER TABLE records ALTER COLUMN file_path TYPE VARCHAR(255)")
    elif dialect == "mysql":
        op.execute("ALTER TABLE records MODIFY COLUMN file_path VARCHAR(255) NOT NULL")
