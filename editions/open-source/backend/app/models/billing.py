from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text
from sqlalchemy.sql import func
from app.db.base import Base
import uuid
from datetime import datetime

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class BillingPlan(Base):
    __tablename__ = "billing_plans"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    code = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    price_monthly = Column(Integer, default=0)
    max_devices = Column(Integer, default=0)
    max_channels = Column(Integer, default=0)
    plugin_entitlements = Column(Text, default="")
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class TenantSubscription(Base):
    __tablename__ = "tenant_subscriptions"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), nullable=False, unique=True, index=True)
    plan_code = Column(String(64), nullable=False, index=True)
    status = Column(String(24), default="active", index=True)
    starts_at = Column(DateTime, default=func.now())
    trial_ends_at = Column(DateTime, nullable=True)
    ends_at = Column(DateTime, nullable=True)
    reminder_sent_at = Column(DateTime, nullable=True)
    machine_code = Column(String(128), nullable=True, index=True)
    machine_code_registered_at = Column(DateTime, nullable=True)
    extra_machine_codes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class TenantBranding(Base):
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
    """
    订阅降级操作日志（用于审计和 affected_plugins 追踪）。
    entitlement_engine.handle_downgrade() 在降级时写入此表。
    """
    __tablename__ = "subscription_downgrade_logs"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), nullable=False, index=True)
    old_plan_code = Column(String(64), nullable=False)
    new_plan_code = Column(String(64), nullable=False)
    affected_plugins = Column(Text, default="[]")
    retains_single = Column(Text, default="[]")
    operator_id = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=func.now())
