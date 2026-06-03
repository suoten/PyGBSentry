import uuid
try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

from sqlalchemy import Column, String, Integer, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base


def generate_uuid():
    return _uuid7_impl().hex


class ConfigRevision(Base):
    __tablename__ = "config_revisions"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    revision = Column(Integer, index=True, nullable=False)
    status = Column(String(24), nullable=False, default="published")
    content = Column(Text, nullable=False, default="{}")
    created_by = Column(String(64), nullable=False, default="system")
    created_at = Column(DateTime, default=func.now(), nullable=False)
