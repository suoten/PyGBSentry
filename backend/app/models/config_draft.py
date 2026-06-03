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


class ConfigDraft(Base):
    __tablename__ = "config_drafts"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    draft_id = Column(String(32), unique=True, index=True, nullable=False)
    base_revision = Column(Integer, nullable=False, default=0)
    status = Column(String(24), nullable=False, default="editing")
    modules = Column(Text, nullable=False, default="{}")
    updated_at = Column(DateTime, default=func.now(), nullable=False)
