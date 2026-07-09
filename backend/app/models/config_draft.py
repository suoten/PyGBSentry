import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class ConfigDraft(Base):
    """配置中心草稿。

    配置中心（``config_center_service``）支持版本化发布：先编辑草稿
    （``status=editing``），校验后发布为新的 ``ConfigRevision``。
    ``modules`` 为 JSON，存储各模块的配置内容。``base_revision`` 标明
    草稿基于哪个已发布版本派生，便于做差异比对与冲突检测。
    """

    __tablename__ = "config_drafts"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    draft_id = Column(String(32), unique=True, nullable=False, index=True)
    base_revision = Column(Integer, nullable=False, default=0)
    status = Column(String(24), nullable=False, default="editing")

    modules = Column(Text, nullable=False, default="{}")

    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), index=True)
    created_at = Column(DateTime, default=func.now())
