from sqlalchemy import Column, String, DateTime, JSON
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class DeviceCluster(Base):
    __tablename__ = "device_clusters"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)
    name = Column(String(128), nullable=False)
    description = Column(String(255), nullable=True)
    rules = Column(JSON, default=dict)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
