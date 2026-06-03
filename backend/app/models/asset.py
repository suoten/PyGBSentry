from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex

class Asset(Base):
    __tablename__ = "assets"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), default="default", index=True)
    organization_id = Column(String(32), nullable=True, index=True, comment="所属组织，用于分级分权")

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

    # Auth — password字段存储加密值，通过decrypted_password属性读取明文
    password = Column(String(256), comment="SIP密码(加密存储)")
    domain = Column(String(64), comment="SIP域")

    @property
    def decrypted_password(self) -> str:
        """Decrypt the stored password. Returns plaintext for SIP Digest Auth."""
        from app.core.field_crypto import decrypt_field
        result = decrypt_field(self.password or "", purpose="sip_password")
        return result if result is not None else ""

    @decrypted_password.setter
    def decrypted_password(self, value: str):
        """Encrypt and store the password."""
        from app.core.field_crypto import encrypt_field
        self.password = encrypt_field(value, purpose="sip_password") if value else ""

    # GB28181 Config
    charset = Column(String(10), default="UTF-8", comment="字符集: UTF-8/GB2312")
    ssrc_check = Column(Boolean, default=False, comment="是否检查SSRC")
    geo_coord_sys = Column(String(10), default="WGS84", comment="地理坐标系: WGS84/GCJ02")
    as_message_channel = Column(Boolean, default=False, comment="作为消息通道")

    # Heartbeat & Subscription Config
    heartbeat_interval = Column(Integer, default=60, comment="心跳间隔")
    heartbeat_count = Column(Integer, default=3, comment="心跳超时次数")
    keepalive_interval = Column(Integer, default=60, comment="Keepalive间隔(秒)，兼容旧字段别名")

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
