import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class Role(Base):
    """角色模型（RBAC）。

    ``code`` 为角色编码（owner / admin / operator / viewer 等），
    ``permission_codes`` 为逗号分隔的权限码列表（``*`` 表示全部权限）。
    系统内置角色 ``is_system=True`` 不可删除。
    与 ``api/deps.py`` 的 ``require_permission`` 配合实现细粒度权限控制。
    """

    __tablename__ = "roles"

    # FIX: [2026-07-17 P1] 添加复合唯一约束，防止同租户下角色 code 重复
    # 否则 RBAC 权限判断可能因多条同 code 记录而混乱
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_role_tenant_code"),
    )

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    code = Column(String(64), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    permission_codes = Column(Text, default="")
    is_system = Column(Boolean, default=False)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
