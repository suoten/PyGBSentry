import uuid
from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from app.db.base import Base
from app.core.field_crypto import encrypt_field, decrypt_field

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class AccessSource(Base):
    """外部流接入源（RTMP/RTSP/GB28181 接入）。

    配置外部流媒体源地址，由 ZLMediaKit 拉取并转码为 GB28181 通道。
    ``gb_*`` 字段将接入源映射为 GB28181 资源（与 ``PushChannel`` 类似，
    但方向相反：此处是拉流接入而非推流接入）。
    ``extra`` 为 JSON，存储协议特定的扩展参数。
    """

    __tablename__ = "access_sources"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    name = Column(String(128), nullable=False)
    protocol = Column(String(32), nullable=False, index=True)
    host = Column(String(128), nullable=False)
    port = Column(Integer, default=0)
    username = Column(String(128), nullable=True)
    password = Column(String(255), nullable=True, comment="接入源密码（AES-256-GCM 密文，base64 编码）")

    @property
    def decrypted_password(self) -> str | None:
        """解密后的明文密码，供拉流鉴权等需要明文的场景使用。

        ``password`` 列始终为密文；本属性读取时解密、赋值时加密，实现对调用方
        透明的字段级加解密。解密失败返回 None（fail-closed）。
        """
        if not self.password:
            return None
        return decrypt_field(self.password, purpose="sip_password")

    @decrypted_password.setter
    def decrypted_password(self, plaintext: str | None) -> None:
        """赋值明文密码时自动加密后写入 ``password`` 列。"""
        if not plaintext:
            self.password = None
            return
        self.password = encrypt_field(plaintext, purpose="sip_password")
    path = Column(String(512), nullable=True)
    stream_name = Column(String(128), nullable=True)

    enabled = Column(Boolean, default=True)
    extra = Column(JSON, default=dict)

    # GB28181 映射
    gb_enabled = Column(Boolean, default=False, index=True)
    gb_id = Column(String(64), nullable=True, index=True)
    gb_name = Column(String(128), nullable=True)
    gb_parent_gb_id = Column(String(64), nullable=True)
    gb_resource_id = Column(String(32), nullable=True, index=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
