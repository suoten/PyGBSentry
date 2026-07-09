"""merge heads: d1e2f3a4b5c6 + g1a2b3c4d5e6

合并两个分叉的 head revision，使 ``alembic upgrade head`` 能正常执行。

分叉原因：
- ``d1e2f3a4b5c6`` (encrypt_media_node_secret) 从 ``c1d2e3f4a5b6`` 延伸
- ``g1a2b3c4d5e6`` (add_stream_id_to_media_port_leases) 从 ``f1a2b3c4d5e6`` 延伸
- 两个迁移各自独立创建，未建立依赖关系，导致 Alembic 报 "Multiple head revisions" 错误

此 merge revision 不做任何 DDL/DML 操作，仅将两个 head 合并为一个。

Revision ID: h1a2b3c4d5e6
Revises: d1e2f3a4b5c6, g1a2b3c4d5e6
Create Date: 2026-07-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = ('d1e2f3a4b5c6', 'g1a2b3c4d5e6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # FIX: [2026-07-03] 合并两个分叉的 head revision，使 alembic upgrade head 可正常执行 [全栈工程师]
    pass


def downgrade() -> None:
    pass
