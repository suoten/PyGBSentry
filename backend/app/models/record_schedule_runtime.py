import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class RecordScheduleRuntime(Base):
    """录像计划运行时状态。

    与 ``RecordSchedule`` 一一对应（按 ``schedule_id``+``resource_id``），
    记录计划求值结果与执行情况：期望是否录像（``desired_recording``）、
    实际是否在录（``is_recording``）、最后一次动作及结果、错误信息等。
    由录像调度任务周期性更新，避免每次重新求值的开销。
    """

    __tablename__ = "record_schedule_runtimes"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    schedule_id = Column(String(32), nullable=False, index=True)
    resource_id = Column(String(32), nullable=False, index=True)

    forced_mode = Column(String(8), nullable=True, comment="手动覆盖模式")
    forced_until = Column(DateTime, nullable=True)

    desired_recording = Column(Boolean, default=False)
    is_recording = Column(Boolean, default=False)

    last_eval_at = Column(DateTime, nullable=True)
    last_stream_seen_at = Column(DateTime, nullable=True)
    last_action_at = Column(DateTime, nullable=True)
    last_action = Column(String(32), nullable=True)
    last_action_ok = Column(Boolean, default=True)
    last_error = Column(Text, nullable=True)
    last_media_node_id = Column(String(32), nullable=True)

    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, default=func.now(), index=True)
