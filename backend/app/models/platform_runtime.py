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


class PlatformRuntime(Base):
    """级联平台运行时状态。

    以 JSON 形式存储平台级联过程中的可变运行时数据（注册状态机、
    目录推送进度、nonce/nc 计数等），避免频繁 ALTER TABLE 添加字段。
    每个平台至多一条记录，按 ``platform_id`` 唯一。
    """

    __tablename__ = "platform_runtimes"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    platform_id = Column(String(32), nullable=False, index=True)
    data = Column(Text, nullable=False, default="{}")

    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
