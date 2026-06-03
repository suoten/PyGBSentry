from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class PlatformRuntime(Base):
    __tablename__ = "platform_runtimes"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    tenant_id = Column(String(64), default="default", index=True)
    platform_id = Column(String(32), index=True, nullable=False)

    data = Column(Text, default="{}")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
