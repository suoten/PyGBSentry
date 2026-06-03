from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class AccessSource(Base):
    __tablename__ = "access_sources"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)
    name = Column(String(128), nullable=False)
    protocol = Column(String(32), nullable=False, index=True)
    host = Column(String(128), nullable=False)
    port = Column(Integer, nullable=False, default=0)
    username = Column(String(128), nullable=True)
    password = Column(String(255), nullable=True)
    path = Column(String(512), nullable=True)
    stream_name = Column(String(128), nullable=True)
    enabled = Column(Boolean, default=True, index=True)
    gb_enabled = Column(Boolean, default=False, index=True)
    gb_id = Column(String(64), nullable=True, index=True)
    gb_name = Column(String(128), nullable=True)
    gb_parent_gb_id = Column(String(64), nullable=True)
    gb_resource_id = Column(String(32), nullable=True, index=True)
    extra = Column(JSON, default={})
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
