from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class AssetStreamPolicy(Base):
    __tablename__ = "asset_stream_policies"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    asset_id = Column(String(32), ForeignKey("assets.id"), unique=True, index=True, nullable=False)
    stream_mode = Column(String(32), default="GLOBAL", nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
