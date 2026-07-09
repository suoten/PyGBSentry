import uuid
from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class AssetStreamPolicy(Base):
    """设备流模式策略。

    按设备（``asset_id`` 唯一）记录当前指定的流模式（UDP/TCP_PASSIVE/
    TCP_ACTIVE）。由自动降级逻辑或管理员手动设置。``sip/invite.py``
    发起 INVITE 时优先读取此策略决定 SDP 中的媒体传输协议。
    """

    __tablename__ = "asset_stream_policies"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    asset_id = Column(String(32), nullable=False, unique=True, index=True)
    stream_mode = Column(String(16), default="UDP", comment="UDP / TCP_PASSIVE / TCP_ACTIVE")

    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, default=func.now())
