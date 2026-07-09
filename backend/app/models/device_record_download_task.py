import uuid
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class DeviceRecordDownloadTask(Base):
    """设备录像下载任务。

    由 ``api/v1/endpoints/device_record.py`` 创建，调度 ZLMediaKit 录制
    GB28181 回放流。``status``: pending / running / completed / failed。
    ``record_ids`` 为 JSON 字符串，记录设备返回的录像段 ID 列表。
    """

    __tablename__ = "device_record_download_tasks"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    asset_id = Column(String(32), nullable=False, index=True)
    resource_id = Column(String(32), nullable=False, index=True)
    stream_session_id = Column(String(32), nullable=True)
    call_id = Column(String(128), nullable=True, index=True)

    app = Column(String(64), nullable=False, default="playback")
    stream = Column(String(64), nullable=False)

    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)

    status = Column(String(24), default="pending", index=True)
    record_ids = Column(Text, default="[]")
    last_error = Column(Text, default="")

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
