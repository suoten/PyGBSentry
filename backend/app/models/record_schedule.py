import uuid
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class RecordSchedule(Base):
    """录像计划。

    按通道（``resource_id``）配置录像策略：``plan_type``:
    timed（按时段）/ continuous（持续）/ motion（移动侦测）。
    ``time_ranges`` 为 JSON 数组，描述每日录像时段，如
    ``[{"start":"08:00","end":"18:00"}]``。由录像调度后台任务读取执行。
    """

    __tablename__ = "record_schedules"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    resource_id = Column(String(32), nullable=False, index=True)
    plan_type = Column(String(24), default="timed", index=True)
    enabled = Column(Boolean, default=True)

    time_ranges = Column(Text, default="[]")
    priority = Column(Integer, default=0)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
