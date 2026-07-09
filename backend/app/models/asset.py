import uuid
from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.sql import func
from app.db.base import Base
from app.core.field_crypto import encrypt_field, decrypt_field

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class Asset(Base):
    """GB28181 设备模型。

    ``gb_id`` 为国标 20 位编码，作为设备在 SIP 信令中的唯一标识。
    ``status``: 0=离线, 1=在线。设备注册/心跳由 ``sip/handlers.py`` 维护。
    ``organization_id`` 支持设备按机构分组（多租户隔离的细粒度补充）。
    """

    __tablename__ = "assets"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)

    # Core Identity
    gb_id = Column(String(20), unique=True, nullable=False, index=True, comment="国标编码")
    name = Column(String(128), comment="设备名称")

    # Network Info
    transport = Column(String(10), default="UDP", comment="传输协议: UDP/TCP")
    ip_addr = Column(String(64), comment="设备IP")
    port = Column(Integer, comment="信令端口")

    # Manufacturer Info
    manufacturer = Column(String(64), comment="厂商")
    model = Column(String(64), comment="型号")
    firmware = Column(String(64), comment="固件版本")

    # Status
    status = Column(Integer, default=0, comment="0: Offline, 1: Online")
    last_keepalive = Column(DateTime, comment="最后心跳时间")
    register_time = Column(DateTime, comment="注册时间")
    expires = Column(Integer, default=3600, comment="注册有效期")

    # FIX: [2026-07-04] Asset 模型仅有整型 status(0/1)，缺失 is_online 布尔映射，
    # 导致 API 消费方读取 is_online 恒为 None。新增计算属性从 status 派生。 [全栈工程师]
    @property
    def is_online(self) -> bool:
        """设备是否在线（从 status 派生，status==1 即在线）。"""
        return self.status == 1

    # Auth — password 列存储 AES-256-GCM 密文（base64），禁止明文落库
    password = Column(String(255), comment="设备密码（AES-256-GCM 密文，base64 编码）")

    @property
    def decrypted_password(self) -> str | None:
        """解密后的明文密码，供 SIP Digest 计算等需要明文的场景使用。

        ``password`` 列始终为密文；本属性读取时解密、赋值时加密，实现对调用方
        透明的字段级加解密。解密失败（密钥变更/数据损坏）返回 None，遵循
        fail-closed 原则，避免将密文误当作明文参与鉴权。
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

    # 组织架构归属
    organization_id = Column(String(32), nullable=True, index=True)

    # GB28181 Extended Fields
    charset = Column(String(10), default="UTF-8")
    ssrc_check = Column(Boolean, default=False)
    geo_coord_sys = Column(String(10), default="WGS84")
    as_message_channel = Column(Boolean, default=False)
    heartbeat_interval = Column(Integer, default=60)
    heartbeat_count = Column(Integer, default=3)
    keepalive_interval = Column(Integer, default=60)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), index=True)
