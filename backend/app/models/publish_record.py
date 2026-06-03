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


class PublishRecord(Base):
    __tablename__ = "publish_records"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    publish_id = Column(String(32), unique=True, index=True, nullable=False)
    from_revision = Column(Integer, nullable=False, default=0)
    to_revision = Column(Integer, nullable=False, default=0)
    operator = Column(String(64), nullable=False, default="system")
    note = Column(Text, nullable=True)
    status = Column(String(24), nullable=False, default="success")
    created_at = Column(DateTime, default=func.now(), nullable=False)
