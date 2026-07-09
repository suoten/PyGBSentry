import uuid
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class OperationAudit(Base):
    """操作审计日志。

    由 ``services/audit_center_service.py`` 统一写入，记录敏感操作
    （登录、配置变更、设备控制等）的模块/动作/操作人/结果/摘要。
    满足等保 2.0 三级审计要求，日志保留 180 天。
    ``tenant_id`` 用于多租户审计隔离。
    """

    __tablename__ = "operation_audits"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    module = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False, index=True)
    operator = Column(String(64), nullable=False, default="unknown", index=True)
    result = Column(String(24), nullable=False, default="success", index=True)

    summary = Column(Text, nullable=False, default="")
    tenant_id = Column(String(36), nullable=True)

    created_at = Column(DateTime, default=func.now(), index=True)
