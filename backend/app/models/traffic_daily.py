import uuid
from sqlalchemy import BigInteger, Column, Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4


def generate_uuid():
    return _uuid7_impl().hex


class TrafficDaily(Base):
    """按通道的每日流量累计(ROADMAP Phase3:流量账单统计)。

    由 ``tasks/traffic_meter.py`` 周期采样 ZLM ``bytesSpeed`` 并按采样间隔折算增量
    累加;``channel_gb_id`` 对未映射到 Resource 的流使用 ZLM 原始流名(resource_id 为空)。
    唯一键 ``(tenant_id, channel_gb_id, day)`` 保证幂等 upsert。
    """

    __tablename__ = "traffic_daily"
    __table_args__ = (UniqueConstraint("tenant_id", "channel_gb_id", "day", name="uq_traffic_daily_channel_day"),)

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    # 通道映射:可映射到 Resource 时为通道 gb_id 并填 resource_id/asset_id;
    # 未映射流(如第三方推流)直接用 ZLM 流名,resource_id 为 NULL
    channel_gb_id = Column(String(64), nullable=False, index=True)
    resource_id = Column(String(32), nullable=True, index=True)
    asset_id = Column(String(32), nullable=True, index=True)

    day = Column(Date, nullable=False, index=True)
    total_bytes = Column(BigInteger, nullable=False, default=0)
    # 当日峰值速率(字节/秒),用于容量评估
    peak_bps = Column(Integer, nullable=False, default=0)

    updated_at = Column(DateTime, nullable=True, onupdate=func.now())
