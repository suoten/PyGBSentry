from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Float
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class Alarm(Base):
    __tablename__ = "alarms"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    device_id = Column(String(20), ForeignKey("assets.gb_id"), nullable=False, index=True)
    channel_id = Column(String(20), index=True) # Optional, some alarms are device level

    # GB28181 Alarm Priority: 1-4
    priority = Column(String(10), default="4")

    # Alarm Method: 1=Telephone, 2=Equipment, 3=SMS, 4=GPS, 5=Video, 6=Manually
    method = Column(String(10))

    # Alarm Time
    time = Column(DateTime, default=func.now(), index=True)

    # Alarm Description
    description = Column(String(255))

    # FIX: [2026-07-04] 模型缺少 Longitude/Latitude 列，移动设备报警的经纬度无法落库 [全栈工程师]
    longitude = Column(Float, nullable=True, comment="报警经度")
    latitude = Column(Float, nullable=True, comment="报警纬度")

    # Alarm Type (e.g., Motion Detection, Video Loss)
    # GB28181 defines codes, we store code or text
    alarm_type = Column(String(64))

    # Status: 0=Unread, 1=Read/Handled
    status = Column(Integer, default=0, index=True)

    created_at = Column(DateTime, default=func.now())
