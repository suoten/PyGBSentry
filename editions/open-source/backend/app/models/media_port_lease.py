import uuid
try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

from sqlalchemy import Column, String, Integer, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.db.base import Base


def generate_uuid():
    return _uuid7_impl().hex


class MediaPortLease(Base):
    """
    媒体收流端口租约（用于 range 模式并发安全分配）。
    通过 (media_server_id, port) 唯一约束避免并发冲突。
    """

    __tablename__ = "media_port_leases"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    media_server_id = Column(String(32), nullable=False, index=True)
    port = Column(Integer, nullable=False)
    stream_session_id = Column(String(32), nullable=True, index=True)
    leased_at = Column(DateTime, default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("media_server_id", "port", name="uq_media_port_leases_server_port"),)

