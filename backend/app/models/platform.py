import uuid
from sqlalchemy import Column, String, Integer, Boolean, DateTime
from app.db.base import Base
from app.core.field_crypto import encrypt_field, decrypt_field

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class ParentPlatform(Base):
    """上级级联平台模型。

    本平台作为下级时，向上级平台注册（``server_gb_id`` 为上级平台国标ID，
    ``client_gb_id`` 为本平台在上级处的国标ID）。级联注册与目录推送由
    ``services/platform_service.py`` 维护。
    """

    __tablename__ = "parent_platforms"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    name = Column(String(128), nullable=False)
    server_gb_id = Column(String(20), nullable=False, unique=True, index=True)
    server_ip = Column(String(64), nullable=False)
    server_port = Column(Integer, default=5060)
    transport = Column(String(8), default="UDP")

    # Local client info for this platform
    client_gb_id = Column(String(20), nullable=False)
    password = Column(String(255), nullable=True, comment="上级平台密码（AES-256-GCM 密文，base64 编码）")

    @property
    def decrypted_password(self) -> str | None:
        """解密后的明文密码，供 SIP Digest 计算等需要明文的场景使用。

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

    # Status
    is_online = Column(Boolean, default=False)
    last_keepalive = Column(DateTime, nullable=True)
    register_interval = Column(Integer, default=3600)
    keepalive_interval = Column(Integer, default=60)

    # 目录推送策略
    catalog_batch_size = Column(Integer, default=0, comment="目录分组推送每批通道数，0=不分组一次全推")
    catalog_push_delay_seconds = Column(Integer, default=0, comment="注册成功后延迟多少秒再首次推送目录，0=立即推送")

    enable = Column(Boolean, default=True, index=True)
