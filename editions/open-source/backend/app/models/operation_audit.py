import uuid
try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base


def generate_uuid():
    return _uuid7_impl().hex


class OperationAudit(Base):
    __tablename__ = "operation_audits"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    module = Column(String(64), index=True, nullable=False)
    action = Column(String(64), nullable=False)
    operator = Column(String(64), nullable=False, default="unknown")
    result = Column(String(24), nullable=False, default="success")
    summary = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=func.now(), nullable=False)
