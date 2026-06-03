"""录像计划：按通道、时间段配置定时/移动侦测/报警联动/手动录像策略。"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class RecordSchedule(Base):
    __tablename__ = "record_schedules"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    resource_id = Column(String(32), ForeignKey("resources.id"), nullable=False, index=True, comment="通道ID")
    # 策略类型: timed=定时, motion=移动侦测, alarm=报警联动, manual=手动
    plan_type = Column(String(24), default="timed", index=True)
    enabled = Column(Boolean, default=True)
    # 时间段配置 JSON: [{"start":"00:00","end":"23:59","days":[0,1,2,3,4,5,6]}], days 0=周一..6=周日
    time_ranges = Column(Text, default="[]", comment="JSON array of {start,end,days}")
    priority = Column(Integer, default=0, comment="优先级，报警联动可高于定时")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
