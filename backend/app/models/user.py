from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.sql import func
from app.db.base import Base
import uuid
from datetime import datetime, timezone

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class User(Base):
    __tablename__ = "users"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    username = Column(String(64), unique=True, nullable=False, index=True)
    hashed_password = Column(String(128), nullable=False)

    email = Column(String(128))
    full_name = Column(String(128))
    tenant_id = Column(String(64), default="default", index=True)
    role = Column(String(32), default="viewer", index=True)

    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)

    totp_enabled = Column(Boolean, default=False)
    totp_secret = Column(String(512), nullable=True)

    # 账户锁定（防止暴力破解）
    failed_login_attempts = Column(Integer, default=0)  # 连续登录失败次数
    locked_until = Column(DateTime, nullable=True)       # 账户锁定截止时间

    @property
    def is_locked(self) -> bool:
        if self.locked_until is None:
            return False
        return self.locked_until.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)

    created_at = Column(DateTime, default=func.now())
    last_login = Column(DateTime)
