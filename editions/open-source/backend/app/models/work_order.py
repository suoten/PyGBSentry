from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class WorkOrder(Base):
    __tablename__ = "work_orders"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)
    alarm_id = Column(String(32), ForeignKey("alarms.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(32), default="other", index=True)
    priority = Column(String(16), default="medium", index=True)
    status = Column(String(24), default="open", index=True)
    assignee_user_id = Column(String(32), ForeignKey("users.id"), nullable=True, index=True)
    created_by_user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    closed_at = Column(DateTime, nullable=True)
