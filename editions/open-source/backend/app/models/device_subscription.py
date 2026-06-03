from sqlalchemy import Column, String, DateTime, Integer, ForeignKey
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class DeviceSubscription(Base):
    __tablename__ = "device_subscriptions"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    asset_id = Column(String(32), ForeignKey("assets.id"), nullable=False, unique=True, index=True)

    catalog_cycle_seconds = Column(Integer, default=0)
    last_catalog_sync_at = Column(DateTime, nullable=True)
    last_catalog_sync_ok = Column(Integer, default=0)
    last_catalog_sync_error = Column(String(500), default="")

    mobile_position_enabled = Column(Integer, default=0)
    mobile_position_interval_seconds = Column(Integer, default=60)
    mobile_position_renew_seconds = Column(Integer, default=300)
    last_mobile_position_subscribe_at = Column(DateTime, nullable=True)
    last_mobile_position_subscribe_ok = Column(Integer, default=0)
    last_mobile_position_subscribe_error = Column(String(500), default="")

    created_at = Column(DateTime, default=func.now(), index=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), index=True)
