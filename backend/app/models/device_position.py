from sqlalchemy import Column, String, Float, DateTime
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class DevicePosition(Base):
    __tablename__ = "device_positions"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    device_id = Column(String(20), nullable=False, index=True, comment="设备国标ID")
    channel_id = Column(String(20), nullable=True, index=True, comment="通道国标ID")
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    speed = Column(Float, nullable=True)
    direction = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)
    time = Column(DateTime, nullable=False, index=True, comment="定位时间")
    created_at = Column(DateTime, default=func.now())
