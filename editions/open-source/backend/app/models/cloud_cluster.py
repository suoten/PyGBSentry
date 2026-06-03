from sqlalchemy import Column, String, DateTime, Boolean, JSON
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class CloudCluster(Base):
    __tablename__ = "cloud_clusters"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)
    name = Column(String(128), nullable=False)
    region = Column(String(64), nullable=True)
    strategy = Column(String(64), default="latency")
    node_ids = Column(JSON, default=[])
    meta = Column(JSON, default={})
    enabled = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
