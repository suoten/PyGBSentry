from sqlalchemy import Column, String, Integer, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class StreamSession(Base):
    __tablename__ = "stream_sessions"

    id = Column(String(32), primary_key=True, default=generate_uuid)

    tenant_id = Column(String(64), default="default", index=True)  # S-04 添加租户隔离

    app = Column(String(64), nullable=False)
    stream = Column(String(64), nullable=False)

    # Relationships
    resource_id = Column(String(32), ForeignKey("resources.id"))
    asset_id = Column(String(32), ForeignKey("assets.id"))
    cascade_platform_id = Column(String(32), ForeignKey("parent_platforms.id"), nullable=True, index=True)

    # SIP Dialog Info
    call_id = Column(String(128), index=True)
    from_tag = Column(String(64))
    to_tag = Column(String(64))
    via_branch = Column(String(64))
    cseq = Column(Integer, default=1)

    cascade_call_id = Column(String(128), nullable=True)
    cascade_from_tag = Column(String(64), nullable=True)
    cascade_to_tag = Column(String(64), nullable=True)

    # Media Info
    ssrc = Column(String(16), index=True)
    media_server_id = Column(String(32)) # ZLM node ID
    media_ip = Column(String(64), nullable=True)  # 节点内网/可达 IP（用于排查/审计）
    media_port = Column(Integer, nullable=True)   # 实际分配的收流端口（支持 range 模式）
    media_port_lease_id = Column(String(32), nullable=True)  # 端口租约ID（用于释放）

    start_time = Column(DateTime, default=func.now())
    protocol = Column(String(10), default="UDP") # UDP, TCP-Active, TCP-Passive
