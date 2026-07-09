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


class PlatformSubscription(Base):
    """级联平台订阅记录。

    记录向上级平台发起的 SIP SUBSCRIBE（目录订阅 / 报警订阅等）状态。
    ``remote_*`` / ``local_*`` 字段保存对话标识，用于后续 NOTIFY 匹配与续订。
    ``(platform_id, event)`` 唯一约束确保同一平台同一事件至多一个活跃订阅。
    """

    __tablename__ = "platform_subscriptions"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    platform_id = Column(String(32), nullable=False, index=True)
    event = Column(String(64), nullable=False, index=True)

    expires_seconds = Column(Integer, default=0)
    expires_at = Column(DateTime, nullable=True, index=True)
    last_subscribe_at = Column(DateTime, nullable=True)
    last_notify_at = Column(DateTime, nullable=True)

    last_addr = Column(String(128), default="")
    last_transport = Column(String(8), default="")
    last_call_id = Column(String(128), default="")

    # 对话标识（用于 NOTIFY 匹配）
    remote_from_tag = Column(String(128), default="")
    local_to_tag = Column(String(128), default="")
    remote_contact = Column(String(512), default="")
    record_route = Column(String(1024), default="")
    notify_cseq = Column(Integer, default=1)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("platform_id", "event", name="uq_platform_subscriptions_platform_event"),
    )
