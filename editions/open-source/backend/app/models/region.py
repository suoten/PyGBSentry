"""行政区域：省-市-县区树形结构，用于设备按地域组织。"""
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

class Region(Base):
    __tablename__ = "regions"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    code = Column(String(32), unique=True, nullable=False, index=True, comment="行政区划代码，如 110000")
    name = Column(String(128), nullable=False)
    parent_id = Column(String(32), nullable=True, index=True, comment="上级区域ID")
    level = Column(Integer, default=0, comment="层级 0省 1市 2区县")
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
