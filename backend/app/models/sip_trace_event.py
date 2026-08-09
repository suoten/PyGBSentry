from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class SipTraceEvent(Base):
    __tablename__ = "sip_trace_events"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)
    trace_id = Column(String(128), index=True, nullable=True)
    event = Column(String(64), index=True, nullable=False)

    platform_id = Column(String(32), index=True, nullable=True)
    device_id = Column(String(64), index=True, nullable=True)
    channel_id = Column(String(64), index=True, nullable=True)

    payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), index=True)

