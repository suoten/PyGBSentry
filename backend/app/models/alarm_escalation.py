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


class AlarmEscalation(Base):
    """告警升级记录。

    跟踪每条告警的升级等级（``escalation_level``）、升级次数与状态
    （open / ack / closed）。``alarm_id`` 唯一：每条告警至多一条升级记录。
    由 ``api/v1/endpoints/alarms.py`` 的升级策略定时巡检触发。
    """

    __tablename__ = "alarm_escalations"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    alarm_id = Column(String(32), unique=True, nullable=False, index=True)
    escalation_level = Column(Integer, default=0)
    escalation_count = Column(Integer, default=0)
    state = Column(String(20), default="open", index=True)

    ack_user_id = Column(String(32), nullable=True)
    ack_at = Column(DateTime, nullable=True)
    last_escalated_at = Column(DateTime, nullable=True)
    escalation_note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
