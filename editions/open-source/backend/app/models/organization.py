"""组织：树形结构，用于分级分权与资产归属。"""
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    name = Column(String(128), nullable=False)
    parent_id = Column(String(32), nullable=True, index=True)
    tenant_id = Column(String(64), default="default", index=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
