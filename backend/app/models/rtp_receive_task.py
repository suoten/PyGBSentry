from sqlalchemy import Column, String, DateTime, Integer, Text
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class RtpReceiveTask(Base):
    __tablename__ = "rtp_receive_tasks"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    node_id = Column(String(32), nullable=False, index=True)
    port = Column(Integer, nullable=False)
    lease_id = Column(String(32), nullable=True, index=True)

    app = Column(String(64), default="live")
    stream_id = Column(String(128), nullable=False, index=True)
    ssrc = Column(String(64), nullable=True)
    tcp_mode = Column(Integer, default=0)

    status = Column(String(24), default="running", index=True)
    last_error = Column(Text, default="")

    created_at = Column(DateTime, default=func.now(), index=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), index=True)

