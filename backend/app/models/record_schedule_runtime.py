from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class RecordScheduleRuntime(Base):
    __tablename__ = "record_schedule_runtimes"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)
    schedule_id = Column(String(32), index=True, nullable=False)
    resource_id = Column(String(32), index=True, nullable=False)

    forced_mode = Column(String(8), nullable=True)  # on | off
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

