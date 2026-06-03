from sqlalchemy import Column, String, DateTime, Boolean, Text
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class UserApiKey(Base):
    __tablename__ = "user_api_keys"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    tenant_id = Column(String(64), default="default", index=True)
    user_id = Column(String(32), index=True, nullable=False)

    name = Column(String(128), nullable=False)
    key_prefix = Column(String(16), index=True, nullable=False)
    hashed_key = Column(String(128), nullable=False)

    scopes = Column(Text, default="[]")
    allowed_ips = Column(Text, default="[]")
    expires_at = Column(DateTime, nullable=True)

    is_active = Column(Boolean, default=True)
    revoked_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=func.now())

