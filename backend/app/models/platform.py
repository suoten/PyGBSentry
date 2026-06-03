from sqlalchemy import Column, String, Integer, Boolean, DateTime
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class ParentPlatform(Base):
    __tablename__ = "parent_platforms"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    name = Column(String(128), nullable=False)
    server_gb_id = Column(String(20), nullable=False, unique=True)
    server_ip = Column(String(64), nullable=False)
    server_port = Column(Integer, default=5060)
    transport = Column(String(8), default="UDP")

    # Local client info for this platform
    client_gb_id = Column(String(20), nullable=False)
    password = Column(String(128))

    # Status
    is_online = Column(Boolean, default=False)
    last_keepalive = Column(DateTime, nullable=True)
    register_interval = Column(Integer, default=3600)
    keepalive_interval = Column(Integer, default=60)
    catalog_batch_size = Column(Integer, default=0, comment="目录分组推送每批通道数，0=不分组一次全推")
    catalog_push_delay_seconds = Column(Integer, default=0, comment="注册成功后延迟多少秒再首次推送目录，0=立即推送")
    enable = Column(Boolean, default=True)
