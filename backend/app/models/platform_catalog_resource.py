import uuid
from sqlalchemy import Column, String, UniqueConstraint
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class PlatformCatalogResource(Base):
    """级联平台-资源映射表。

    记录向上级平台推送的通道清单。``virtual_gb_id`` 等字段支持为本地通道
    分配上级可见的虚拟国标ID（避免与上级已有通道冲突）。
    ``(platform_id, resource_id)`` 唯一约束防止重复推送。
    """

    __tablename__ = "platform_catalog_resources"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    platform_id = Column(String(32), nullable=False, index=True)
    resource_id = Column(String(32), nullable=False, index=True)

    virtual_gb_id = Column(String(64), nullable=True)
    virtual_name = Column(String(128), nullable=True)
    virtual_parent_id = Column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("platform_id", "resource_id", name="uq_platform_catalog_resource"),
    )
