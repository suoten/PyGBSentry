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


class AssetStreamHealth(Base):
    """设备流媒体健康度统计。

    按设备（``asset_id`` 唯一）累计成功/失败次数、连续失败次数、自动切换次数。
    由 ``sip/response_handler.py`` 在每次拉流响应后更新。连续失败达到阈值时
    触发自动降级（UDP→TCP_PASSIVE→TCP_ACTIVE），见 ``AssetStreamPolicy``。
    """

    __tablename__ = "asset_stream_health"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    asset_id = Column(String(32), nullable=False, unique=True, index=True)

    last_status_code = Column(Integer, nullable=True)
    last_mode = Column(String(16), nullable=True, comment="最后一次成功的流模式 UDP/TCP_PASSIVE/...")

    success_total = Column(Integer, default=0)
    fail_total = Column(Integer, default=0)
    consecutive_failures = Column(Integer, default=0)
    auto_switch_count = Column(Integer, default=0)

    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, default=func.now())
