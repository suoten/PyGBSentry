"""结构化事件（人脸/车牌/行为等），供统一检索与以图搜图扩展。"""
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


class StructuredEvent(Base):
    __tablename__ = "structured_events"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)
    source_plugin = Column(String(64), index=True)  # face_recognition_suite | plate_recognition_suite | behavior_recognition_suite
    event_type = Column(String(32), nullable=False, index=True)  # face | plate | behavior
    device_id = Column(String(64), index=True)
    channel_id = Column(String(64), index=True)
    event_time = Column(DateTime, nullable=False, index=True)
    payload = Column(Text, nullable=True)  # JSON
    created_at = Column(DateTime, default=func.now(), index=True)
