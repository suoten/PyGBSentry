import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class UserApiKey(Base):
    """用户 API 密钥。

    用于程序化访问 API（替代 JWT）。密钥以 ``prefix.raw`` 形式展示给用户一次，
    数据库仅存储 ``hashed_key``（HMAC-SHA256）。``key_prefix`` 用于初筛候选记录，
    再用 ``secure_compare`` 做恒定时间比较防时序攻击。
    跨机构操作必须校验 ``tenant_id`` 范围，禁止跨机构身份冒用。
    """

    __tablename__ = "user_api_keys"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)
    user_id = Column(String(32), nullable=False, index=True)

    name = Column(String(128), nullable=False, comment="密钥名称（用户自定义）")
    key_prefix = Column(String(16), nullable=False, index=True)
    hashed_key = Column(String(128), nullable=False)

    scopes = Column(Text, default="[]", comment="JSON 数组，授权作用域")
    allowed_ips = Column(Text, default="[]", comment="JSON 数组，IP 白名单")

    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    revoked_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=func.now())
