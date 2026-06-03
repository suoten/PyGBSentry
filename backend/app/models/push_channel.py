from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.base import Base


import uuid as _uuid_mod

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = _uuid_mod.uuid4


def generate_uuid() -> str:
    """Generate a 32-character hex UUID, consistent with all other models in this codebase."""
    return _uuid7_impl().hex


class PushChannel(Base):
    __tablename__ = "push_channels"

    id = Column(String(32), primary_key=True, default=generate_uuid)  # S-01 添加UUID生成器，与项目其他48个模型保持一致

    tenant_id = Column(String(64), default="default", index=True)

    stream_name = Column(String(128), nullable=False, index=True)

    push_key_enabled = Column(Boolean, default=False)
    push_key_prefix = Column(String(16), index=True, nullable=True)
    hashed_push_key = Column(String(128), nullable=True)

    gb_enabled = Column(Boolean, default=False)
    gb_resource_id = Column(String(32), ForeignKey("resources.id"), nullable=True, index=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

