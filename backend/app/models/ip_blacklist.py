import uuid
from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class IpBlacklist(Base):
    """SIP / API IP 黑名单。

    触发条件：1) 手动添加（运维端点）；2) 5 分钟内鉴权失败 ≥5 次自动拉黑
    （见 ``sip/handlers.py``）。``sip/server.py`` 启动时加载到内存缓存，
    并定期（``blacklist_ttl``）从数据库重新加载以同步外部变更。
    """

    __tablename__ = "ip_blacklist"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    ip = Column(String(64), nullable=False, unique=True, index=True)
    reason = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=func.now())
