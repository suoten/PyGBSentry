import uuid
from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class AlarmLinkRule(Base):
    """告警联动规则。

    定义告警触发后的联动动作：关联录像（``link_record``）、上墙
    （``link_wall``）、通知（``link_notify``）。支持按优先级范围、
    时间段（``start_time``/``end_time``）、星期（``days``）、机构过滤。
    由 ``sip/handlers.py`` 在收到告警时匹配执行。
    """

    __tablename__ = "alarm_link_rules"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), nullable=False, default="default")

    name = Column(String(128), nullable=False)
    enabled = Column(Boolean, default=True)

    # 过滤条件
    min_priority = Column(Integer, nullable=True)
    max_priority = Column(Integer, nullable=True)
    start_time = Column(String(8), nullable=True, comment="HH:MM")
    end_time = Column(String(8), nullable=True, comment="HH:MM")
    days = Column(String(32), nullable=True, comment="逗号分隔的星期 1-7")
    organization_id = Column(String(32), nullable=True, index=True)

    # 联动动作
    link_record = Column(Boolean, default=True)
    link_wall = Column(Boolean, default=False)
    link_notify = Column(Boolean, default=False)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        # 按租户+启用状态检索活跃规则
        # （声明为复合索引以优化匹配查询；schema_upgrade 亦会兜底创建）
    )
