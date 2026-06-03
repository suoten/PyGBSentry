from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid() -> str:
    return _uuid7_impl().hex


class NetworkMetric(Base):
    __tablename__ = "network_metrics"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    metric = Column(String(32), nullable=False, index=True)  # active_streams, estimated_bandwidth
    value = Column(Integer, nullable=False)

    created_at = Column(DateTime, default=func.now(), index=True)

