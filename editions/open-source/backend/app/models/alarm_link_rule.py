from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class AlarmLinkRule(Base):
    """
    报警联动规则：
    - 按优先级范围 / 时间段 / 星期 / 组织等条件，决定是否触发录像/上墙/通知等联动。
    - 先只控制“录像联动”（是否触发 HOOK_ALARM_RECORD_LINK），后续可扩展其他动作。
    """

    __tablename__ = "alarm_link_rules"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)
    name = Column(String(128), nullable=False)
    enabled = Column(Boolean, default=True, index=True)

    # GB28181 priority 范围（1=最高，4=最低），为空表示不限制
    min_priority = Column(Integer, nullable=True)
    max_priority = Column(Integer, nullable=True)

    # 时间段（本地时间，HH:MM），为空表示不限制
    start_time = Column(String(8), nullable=True)
    end_time = Column(String(8), nullable=True)

    # 星期限制：逗号分隔的 0-6（0=周一），空表示不限制
    days = Column(String(32), nullable=True)

    # 组织限制：assets.organization_id，空表示不限制
    organization_id = Column(String(32), nullable=True, index=True)

    # 联动动作（当前只实现录像联动；其他动作保留字段）
    link_record = Column(Boolean, default=True)
    link_wall = Column(Boolean, default=False)
    link_notify = Column(Boolean, default=False)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

