from sqlalchemy import Column, String, Integer, BigInteger, DateTime, ForeignKey, Float, Boolean, Text, Index
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class Record(Base):
    __tablename__ = "records"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    asset_id = Column(String(32), ForeignKey("assets.id"), nullable=False, index=True)
    resource_id = Column(String(32), ForeignKey("resources.id"), nullable=False, index=True)

    start_time = Column(DateTime, nullable=False, index=True)
    # FIX R22-GENERAL: end_time 添加索引（query_records/search_records 都用 Record.end_time <= end_time 过滤）
    end_time = Column(DateTime, nullable=False, index=True)
    duration = Column(Float, comment="Duration in seconds")

    file_path = Column(String(255), nullable=False) # Local path or URL
    file_size = Column(BigInteger, default=0)

    # FIX R22-GENERAL: stream_id 添加索引（hook 回调、流清理、录像去重都按 stream_id 查询）
    stream_id = Column(String(64), index=True) # ZLM stream ID

    tenant_id = Column(String(64), default="default", index=True)
    record_app = Column(String(32), nullable=True, index=True)
    media_node_id = Column(String(32), nullable=True, index=True)
    zlm_file_path = Column(String(512), nullable=True)

    url_checked_at = Column(DateTime, nullable=True, index=True)
    url_ok = Column(Boolean, default=True, index=True)
    url_status_code = Column(Integer, nullable=True)
    url_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=func.now())

    # FIX R22-GENERAL: 添加复合索引，优化按通道+时间范围查询录像的常见场景
    __table_args__ = (
        Index("ix_records_resource_start_end", "resource_id", "start_time", "end_time"),
        Index("ix_records_tenant_start_time", "tenant_id", "start_time"),
    )
