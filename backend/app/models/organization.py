import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class Organization(Base):
    """组织机构模型（树形结构）。

    ``parent_id`` 自引用形成层级。设备（``Asset.organization_id``）可归属
    某机构，实现多机构分组管理。``sort_order`` 控制同层排序。
    """

    __tablename__ = "organizations"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    name = Column(String(128), nullable=False)
    # FIX: [2026-07-17 P1] 添加自引用 ForeignKey，防止脏数据；RESTRICT 阻止删除有子节点的组织
    parent_id = Column(String(32), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True, index=True)
    tenant_id = Column(String(64), default="default", index=True)
    sort_order = Column(Integer, default=0)

    # FIX: [2026-07-17 P1] 建立 ORM 关系，便于 eager loading
    children = relationship("Organization", backref="parent", remote_side=[id], lazy="selectin")

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
