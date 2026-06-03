from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class AlarmEscalation(Base):
    __tablename__ = "alarm_escalations"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    alarm_id = Column(String(32), ForeignKey("alarms.id"), nullable=False, unique=True, index=True)
    escalation_level = Column(Integer, default=0, index=True)
    escalation_count = Column(Integer, default=0)
    state = Column(String(20), default="open", index=True)
    ack_user_id = Column(String(32), ForeignKey("users.id"), nullable=True)
    ack_at = Column(DateTime, nullable=True)
    last_escalated_at = Column(DateTime, nullable=True)
    escalation_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
