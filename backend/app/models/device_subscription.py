import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class DeviceSubscription(Base):
    """设备订阅记录。

    记录对下级设备的 SIP SUBSCRIBE 状态：目录同步（catalog）与
    移动位置（mobile_position）。``last_catalog_sync_ok`` /
    ``last_mobile_position_subscribe_ok`` 为 0/1 标志位（兼容旧库 INTEGER）。
    ``asset_id`` 唯一约束确保每台设备至多一条订阅配置。
    """

    __tablename__ = "device_subscriptions"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    # P2-01: 添加 ForeignKey 级联删除约束，设备删除时自动清理订阅记录
    asset_id = Column(String(32), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # 目录同步
    catalog_cycle_seconds = Column(Integer, default=0)
    last_catalog_sync_at = Column(DateTime, nullable=True)
    last_catalog_sync_ok = Column(Integer, default=0)
    last_catalog_sync_error = Column(String(500), default="")

    # 移动位置订阅
    mobile_position_enabled = Column(Integer, default=0)
    mobile_position_interval_seconds = Column(Integer, default=60)
    mobile_position_renew_seconds = Column(Integer, default=300)
    last_mobile_position_subscribe_at = Column(DateTime, nullable=True)
    last_mobile_position_subscribe_ok = Column(Integer, default=0)
    last_mobile_position_subscribe_error = Column(String(500), default="")

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
