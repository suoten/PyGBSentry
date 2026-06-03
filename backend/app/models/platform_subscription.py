from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class PlatformSubscription(Base):
    __tablename__ = "platform_subscriptions"
    __table_args__ = (UniqueConstraint("platform_id", "event", name="uq_platform_subscriptions_platform_event"),)

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    platform_id = Column(String(32), ForeignKey("parent_platforms.id"), nullable=False, index=True)
    event = Column(String(64), nullable=False, index=True)

    expires_seconds = Column(Integer, default=0)
    expires_at = Column(DateTime, nullable=True, index=True)

    last_subscribe_at = Column(DateTime, nullable=True)
    last_notify_at = Column(DateTime, nullable=True)

    last_addr = Column(String(128), default="")
    last_transport = Column(String(8), default="")
    last_call_id = Column(String(128), default="")
    remote_from_tag = Column(String(128), default="")
    local_to_tag = Column(String(128), default="")
    remote_contact = Column(String(512), default="")
    record_route = Column(String(1024), default="")
    notify_cseq = Column(Integer, default=1)

    created_at = Column(DateTime, default=func.now(), index=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), index=True)
