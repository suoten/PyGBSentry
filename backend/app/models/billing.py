import uuid
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, JSON
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class BillingPlan(Base):
    """计费方案。

    开源版默认内置 ``community`` 方案（免费，max_devices/max_channels=0 表示不限）。
    服务器版通过此表管理多档付费方案，``plugin_entitlements`` 为 JSON 字符串，
    描述方案包含的插件授权清单。
    """

    __tablename__ = "billing_plans"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    code = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    price_monthly = Column(Integer, default=0, comment="月付价格（分）")
    price_yearly = Column(Integer, nullable=True, comment="年付价格（分）")
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)
    max_devices = Column(Integer, default=0, comment="0=不限")
    max_channels = Column(Integer, default=0, comment="0=不限")
    plugin_entitlements = Column(Text, default="")
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class TenantSubscription(Base):
    """租户订阅记录。

    每个租户（``tenant_id``）至多一条有效订阅。``status``:
    active / trial / expired / suspended。``machine_code`` 用于在线授权认证，
    防止 license 被复制到其他机器。
    """

    __tablename__ = "tenant_subscriptions"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), nullable=False, unique=True, index=True)
    plan_code = Column(String(64), nullable=False, index=True)
    status = Column(String(24), default="active", index=True)
    starts_at = Column(DateTime, default=func.now())
    trial_ends_at = Column(DateTime, nullable=True)
    ends_at = Column(DateTime, nullable=True)
    reminder_sent_at = Column(DateTime, nullable=True)

    # 机器码绑定（在线授权认证）
    machine_code = Column(String(128), nullable=True, index=True)
    machine_code_registered_at = Column(DateTime, nullable=True)
    # 多实例/多节点支持：允许多个机器码（逗号分隔的哈希列表）
    extra_machine_codes = Column(Text, nullable=True)
    # 降级历史记录（JSON）
    downgrade_history = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
