import uuid
from sqlalchemy import Column, String, Integer, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class MediaPortLease(Base):
    """媒体节点 RTP 端口租约。

    每次拉流时从媒体节点端口范围内分配一个端口，会话结束后释放。
    ``(media_server_id, port)`` 唯一约束防止端口重复分配。
    ``stream_session_id`` 关联占用该端口的流会话，用于会话结束时精确释放。
    """

    __tablename__ = "media_port_leases"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    media_server_id = Column(String(32), nullable=False, index=True)
    port = Column(Integer, nullable=False)
    stream_session_id = Column(String(32), nullable=True, index=True)
    # FIX: [2026-07-03] 增加 stream_id/app_name 字段，用于孤儿租约清理时关闭 ZLM RTP Server [全栈工程师]
    stream_id = Column(String(128), nullable=True)
    app_name = Column(String(64), nullable=True)

    leased_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint("media_server_id", "port", name="uq_media_port_leases_server_port"),
    )
