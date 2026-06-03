"""设备维保记录：设备台账、维保记录、生命周期管理。"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class AssetMaintenance(Base):
    __tablename__ = "asset_maintenances"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    asset_id = Column(String(32), ForeignKey("assets.id"), nullable=False, index=True)
    maintenance_type = Column(String(32), default="routine", comment="routine=例行, repair=维修, upgrade=升级, replace=更换")
    maintenance_date = Column(DateTime, nullable=False)
    note = Column(Text)
    operator = Column(String(64))
    created_at = Column(DateTime, default=func.now())
