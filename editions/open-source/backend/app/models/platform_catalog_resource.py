"""级联目录推送范围：某上级平台仅接收指定通道（直播推流转发可选通道）。"""
from sqlalchemy import Column, String, UniqueConstraint
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class PlatformCatalogResource(Base):
    __tablename__ = "platform_catalog_resources"
    __table_args__ = (UniqueConstraint("platform_id", "resource_id", name="uq_platform_catalog"),)

    id = Column(String(32), primary_key=True, default=generate_uuid)
    platform_id = Column(String(32), nullable=False, index=True)
    resource_id = Column(String(32), nullable=False, index=True)

    # 级联目录推送时的虚拟目录与 ID 重映射
    virtual_gb_id = Column(String(64), nullable=True, comment="推给上级时的伪装ID")
    virtual_name = Column(String(128), nullable=True, comment="推给上级时的伪装名称")
    virtual_parent_id = Column(String(64), nullable=True, comment="挂载的上级虚拟目录ID")
