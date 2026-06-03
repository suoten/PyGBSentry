from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class AssetStreamHealth(Base):
    __tablename__ = "asset_stream_health"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    asset_id = Column(String(32), ForeignKey("assets.id"), unique=True, index=True, nullable=False)
    last_mode = Column(String(32), default="UDP", nullable=False)
    last_status_code = Column(Integer, default=0, nullable=False)
    success_total = Column(Integer, default=0, nullable=False)
    fail_total = Column(Integer, default=0, nullable=False)
    consecutive_failures = Column(Integer, default=0, nullable=False)
    auto_switch_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
