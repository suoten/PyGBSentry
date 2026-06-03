from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class DeviceRecordDownloadTask(Base):
    __tablename__ = "device_record_download_tasks"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    tenant_id = Column(String(64), default="default", index=True)

    asset_id = Column(String(32), ForeignKey("assets.id"), nullable=False, index=True)
    resource_id = Column(String(32), ForeignKey("resources.id"), nullable=False, index=True)

    stream_session_id = Column(String(32), ForeignKey("stream_sessions.id"), nullable=True, index=True)
    call_id = Column(String(128), nullable=True, index=True)
    app = Column(String(64), nullable=False, default="playback")
    stream = Column(String(64), nullable=False)

    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)

    status = Column(String(24), default="pending", index=True)
    record_ids = Column(Text, default="[]")
    last_error = Column(Text, default="")

    created_at = Column(DateTime, default=func.now(), index=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), index=True)

