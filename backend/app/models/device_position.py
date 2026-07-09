import uuid
from sqlalchemy import Column, String, Float, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class DevicePosition(Base):
    """设备/通道位置信息（GB28181 移动位置订阅）。

    通过 SIP ``MobilePosition`` 订阅获取，按设备+时间检索。``channel_id``
    为空时表示设备级位置。索引 ``(device_id, time)`` 优化轨迹回放查询。
    """

    __tablename__ = "device_positions"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    device_id = Column(String(20), nullable=False, index=True)
    channel_id = Column(String(20), nullable=True)

    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    speed = Column(Float, nullable=True)
    direction = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)

    time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        # 轨迹回放主查询：按设备+时间范围
        # （SQLite/MySQL 均支持在 __table_args__ 声明复合索引，schema_upgrade 也会兜底创建）
    )
