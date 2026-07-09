import uuid
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class PushChannel(Base):
    """推流通道（GB28181 推流接入）。

    将外部流源（RTMP/RTSP）通过 ZLMediaKit 转码后以 GB28181 通道形式
    注册到本平台。``push_key_*`` 为推流鉴权密钥（哈希存储），
    ``gb_*`` 字段将该推流映射为一个 GB28181 资源。
    """

    __tablename__ = "push_channels"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    stream_name = Column(String(128), nullable=False, index=True)

    # 推流鉴权
    push_key_enabled = Column(Boolean, default=False)
    push_key_prefix = Column(String(16), nullable=True, index=True)
    hashed_push_key = Column(String(128), nullable=True)

    # GB28181 映射
    gb_enabled = Column(Boolean, default=False)
    gb_resource_id = Column(String(32), nullable=True, index=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
