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


class User(Base):
    """用户模型。

    系统账号（admin/operator/viewer）与租户隔离通过 ``tenant_id`` 实现。
    账户锁定（``failed_login_attempts`` / ``locked_until``）用于防御暴力破解，
    与 ``api/deps.py`` 的登录失败计数逻辑配合使用。
    """

    __tablename__ = "users"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    username = Column(String(64), unique=True, nullable=False, index=True)
    hashed_password = Column(String(128), nullable=False)

    email = Column(String(128))
    full_name = Column(String(128))
    auth_domain = Column(String(16), default="tenant", index=True)
    tenant_id = Column(String(64), default="default", index=True)
    role = Column(String(32), default="viewer", index=True)
    site_role = Column(String(32), default="normal", index=True)

    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)

    # 账户锁定：失败次数累计达到阈值后锁定至 locked_until
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)

    # TOTP 两步验证
    totp_enabled = Column(Boolean, default=False)
    totp_secret = Column(String(64), nullable=True)

    # 合规协议版本（服务条款 / 隐私政策）
    agreed_tos_version = Column(String(32), nullable=True)
    agreed_privacy_version = Column(String(32), nullable=True)
    agreed_dev_version = Column(String(32), nullable=True)

    created_at = Column(DateTime, default=func.now())
    last_login = Column(DateTime, nullable=True)
