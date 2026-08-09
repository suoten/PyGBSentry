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


# FIX: [2026-07-13] 以下三个模型类从 2ad636a 恢复 — billing 端点导入
# TenantBranding/PluginOrder/SubscriptionDowngradeLog 但 ConvergeLoop Round 0
# 将它们删除，导致 billing 端点导入失败、/api/v1/billing/* 全部 404。[全栈工程师]

class TenantBranding(Base):
    """租户品牌定制（产品名、Logo、主题色等）。"""

    __tablename__ = "tenant_branding"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), nullable=False, unique=True, index=True)
    product_name = Column(String(128), default="PyGBSentry")
    logo_url = Column(String(255), nullable=True)
    primary_color = Column(String(16), default="#1f2937")
    welcome_text = Column(String(255), default="Welcome to PyGBSentry")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class PluginOrder(Base):
    """插件订单记录。"""

    __tablename__ = "plugin_orders"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    order_no = Column(String(64), nullable=False, unique=True, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(32), nullable=False, index=True)
    plugin_id = Column(String(64), nullable=False, index=True)
    plugin_name = Column(String(128), nullable=False)
    amount = Column(Integer, default=0)
    currency = Column(String(8), default="CNY")
    status = Column(String(24), default="pending", index=True)
    pay_channel = Column(String(32), default="pending")
    paid_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    callback_payload = Column(Text, nullable=True)
    license_data = Column(Text, nullable=True)
    billing_period = Column(String(16), nullable=True)
    quantity = Column(Integer, default=1)
    order_type = Column(String(24), default="license")
    upgrade_policy = Column(String(24), nullable=True)
    version_major = Column(String(16), nullable=True)
    maintenance_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class SubscriptionDowngradeLog(Base):
    """订阅降级操作日志（用于审计和 affected_plugins 追踪）。"""

    __tablename__ = "subscription_downgrade_logs"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), nullable=False, index=True)
    old_plan_code = Column(String(64), nullable=False)
    new_plan_code = Column(String(64), nullable=False)
    affected_plugins = Column(Text, default="[]")
    retains_single = Column(Text, default="[]")
    operator_id = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=func.now())
