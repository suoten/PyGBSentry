from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid() -> str:
    return _uuid7_impl().hex


class AlarmNotification(Base):
    __tablename__ = "alarm_notifications"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    alarm_id = Column(String(32), index=True)
    device_id = Column(String(32), index=True)
    channel_id = Column(String(32), index=True)

    channel = Column(String(16), index=True)  # sms / wecom / feishu / webhook 等
    status = Column(String(16), index=True)  # success / fail
    error_message = Column(Text, nullable=True)

    description = Column(String(255), nullable=True)

    sent_at = Column(DateTime, default=func.now(), index=True)
    created_at = Column(DateTime, default=func.now())

