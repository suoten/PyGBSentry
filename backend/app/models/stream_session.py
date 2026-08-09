import uuid
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class StreamSession(Base):
    """流会话模型。

    记录一次点播/回放/级联拉流的完整 SIP 对话状态，包括 Call-ID、SSRC、
    媒体节点、收发地址等。``media_port_lease_id`` 关联 RTP 端口租约，
    会话结束时由 ``stream_session_service`` 释放。
    ``cascade_*`` 字段用于级联场景下区分本地对话与上级对话。
    """

    __tablename__ = "stream_sessions"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    app = Column(String(64), nullable=False)
    stream = Column(String(64), nullable=False)

    resource_id = Column(String(32), nullable=True, index=True)
    asset_id = Column(String(32), nullable=True, index=True)
    cascade_platform_id = Column(String(32), nullable=True, index=True)

    call_id = Column(String(128), nullable=True, index=True)
    from_tag = Column(String(64), nullable=True)
    to_tag = Column(String(64), nullable=True)
    via_branch = Column(String(64), nullable=True)
    cseq = Column(Integer, nullable=True)

    # 级联场景下上级对话的标识
    cascade_call_id = Column(String(128), nullable=True)
    cascade_from_tag = Column(String(64), nullable=True)
    cascade_to_tag = Column(String(64), nullable=True)

    ssrc = Column(String(16), nullable=True, index=True)
    media_server_id = Column(String(32), nullable=True, index=True)
    media_ip = Column(String(64), nullable=True)
    media_port = Column(Integer, nullable=True)
    media_port_lease_id = Column(String(32), nullable=True)

    start_time = Column(DateTime, default=func.now())
    # FIX: [2026-07-16] String(10) 无法完整存储 "TCP-PASSIVE"（11 字符），会被截断为
    # "TCP-PASSIV"，导致 response_handler.py 中 protocol == "TCP-PASSIVE" 判断永远为 False，
    # SSRC 恢复时 RTP 服务器以错误模式（UDP）重开。提升到 String(16)。
    protocol = Column(String(16), default="UDP")
