from sqlalchemy import Column, String, Integer, BigInteger, DateTime, ForeignKey, Float, Boolean, Text
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
    end_time = Column(DateTime, nullable=False)
    duration = Column(Float, comment="Duration in seconds")

    file_path = Column(String(255), nullable=False) # Local path or URL
    file_size = Column(BigInteger, default=0)

    stream_id = Column(String(64)) # ZLM stream ID

    tenant_id = Column(String(64), default="default", index=True)
    record_app = Column(String(32), nullable=True, index=True)
    media_node_id = Column(String(32), nullable=True, index=True)
    zlm_file_path = Column(String(512), nullable=True)

    url_checked_at = Column(DateTime, nullable=True, index=True)
    url_ok = Column(Boolean, default=True, index=True)
    url_status_code = Column(Integer, nullable=True)
    url_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=func.now())
