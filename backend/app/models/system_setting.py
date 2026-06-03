from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    setting_key = Column(String(128), unique=True, index=True, nullable=False)
    setting_value = Column(String(2000), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
