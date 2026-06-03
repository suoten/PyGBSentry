from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.base import Base


class PushChannel(Base):
    __tablename__ = "push_channels"

    id = Column(String(32), primary_key=True)

    tenant_id = Column(String(64), default="default", index=True)

    stream_name = Column(String(128), nullable=False, index=True)

    push_key_enabled = Column(Boolean, default=False)
    push_key_prefix = Column(String(16), index=True, nullable=True)
    hashed_push_key = Column(String(128), nullable=True)

    gb_enabled = Column(Boolean, default=False)
    gb_resource_id = Column(String(32), ForeignKey("resources.id"), nullable=True, index=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

