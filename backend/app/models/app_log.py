"""App 端崩溃/行为日志（手机版、小程序上报）。"""
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid() -> str:
    return _uuid7_impl().hex


class AppLog(Base):
    __tablename__ = "app_logs"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    plugin_id = Column(String(64), index=True)   # mobile_app_suite | mini_program_suite
    app_version = Column(String(32), index=True)
    platform = Column(String(32), index=True)    # android | ios | miniprogram
    log_type = Column(String(32), index=True)    # crash | behavior
    message = Column(Text, nullable=True)
    extra = Column(Text, nullable=True)          # JSON 等扩展信息

    created_at = Column(DateTime, default=func.now(), index=True)
