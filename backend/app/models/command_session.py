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


class CommandSession(Base):
    __tablename__ = "command_sessions"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)
    alarm_id = Column(String(32), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    status = Column(String(24), nullable=False, default="open", index=True)
    started_by_user_id = Column(String(32), nullable=True)
    started_at = Column(DateTime, default=func.now(), nullable=False)
    ended_at = Column(DateTime, nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
