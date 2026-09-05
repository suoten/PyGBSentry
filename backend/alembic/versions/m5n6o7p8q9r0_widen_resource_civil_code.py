"""widen resources.civil_code and node_type columns

Revision ID: m5n6o7p8q9r0
Revises: l4e5f6a7b8c9d
Create Date: 2026-08-17

设备返回的 CivilCode 值可能超过 VARCHAR(16) 限制（如 20 位 GB28181 行政区划编码），
导致 StringDataRightTruncationError，使整个 catalog 同步失败（71 个通道全部丢失）。
本迁移将 civil_code 从 VARCHAR(16) 扩宽到 VARCHAR(64)，node_type 从 VARCHAR(16) 扩宽到 VARCHAR(32)。
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "m5n6o7p8q9r0"
down_revision = "l4e5f6a7b8c9d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute("ALTER TABLE resources ALTER COLUMN civil_code TYPE VARCHAR(64)")
        op.execute("ALTER TABLE resources ALTER COLUMN node_type TYPE VARCHAR(32)")
    else:
        with op.batch_alter_table("resources") as batch_op:
            batch_op.alter_column(
                "civil_code",
                existing_type=sa.String(16),
                type_=sa.String(64),
                existing_nullable=True,
            )
            batch_op.alter_column(
                "node_type",
                existing_type=sa.String(16),
                type_=sa.String(32),
                existing_nullable=True,
            )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute("ALTER TABLE resources ALTER COLUMN civil_code TYPE VARCHAR(16)")
        op.execute("ALTER TABLE resources ALTER COLUMN node_type TYPE VARCHAR(16)")
    else:
        with op.batch_alter_table("resources") as batch_op:
            batch_op.alter_column(
                "civil_code",
                existing_type=sa.String(64),
                type_=sa.String(16),
                existing_nullable=True,
            )
            batch_op.alter_column(
                "node_type",
                existing_type=sa.String(32),
                type_=sa.String(16),
                existing_nullable=True,
            )
