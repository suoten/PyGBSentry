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

class IpBlacklist(Base):
    __tablename__ = "ip_blacklist"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    ip = Column(String(50), unique=True, index=True, nullable=False)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())
