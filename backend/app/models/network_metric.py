import uuid
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class NetworkMetric(Base):
    """网络指标时序数据。

    记录 SIP 信令量、媒体流路数等指标，供报表端点
    （``api/v1/endpoints/reports.py``）绘制趋势图。按 ``(metric, created_at)``
    复合索引优化时间范围聚合查询。
    """

    __tablename__ = "network_metrics"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    metric = Column(String(32), nullable=False)
    value = Column(Integer, nullable=False)

    created_at = Column(DateTime, default=func.now(), index=True)
